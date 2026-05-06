from __future__ import annotations

import asyncio
from datetime import date
import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

from app.schemas import NewsItem

STOPWORDS = {"de", "da", "do", "das", "dos", "e"}
REQUEST_DELAY_SECONDS = 0.35
MAX_ARTICLE_FETCHES_MULTIPLIER = 4
MAX_LISTING_PAGES = 20


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    without_accents = "".join(
        char for char in normalized if not unicodedata.combining(char)
    )
    cleaned = re.sub(r"[^a-zA-Z0-9\s]", " ", without_accents.casefold())
    return re.sub(r"\s+", " ", cleaned).strip()


def tokenize(value: str) -> list[str]:
    return [token for token in normalize_text(value).split(" ") if token]


def build_name_variants(name: str) -> set[str]:
    tokens = tokenize(name)
    if not tokens:
        return set()

    significant_tokens = [token for token in tokens if token not in STOPWORDS]
    if not significant_tokens:
        significant_tokens = tokens

    variants = {
        " ".join(tokens),
        " ".join(significant_tokens),
        f"{significant_tokens[0]} {significant_tokens[-1]}",
    }

    initials = [token[0] for token in significant_tokens[:-1] if token]
    if len(initials) >= 2:
        variants.add(f"{' '.join(initials)} {significant_tokens[-1]}")
    if initials:
        variants.add(f"{initials[0]} {significant_tokens[-1]}")

    return {variant.strip() for variant in variants if variant.strip()}


def match_names_in_text(
    names: list[str],
    searchable_text: str,
    name_variants: dict[str, set[str]],
) -> list[str]:
    normalized_searchable_text = normalize_text(searchable_text)

    matched_names: list[str] = []
    for name in names:
        variants = name_variants.get(name, set())
        if any(
            variant and variant in normalized_searchable_text for variant in variants
        ):
            matched_names.append(name)

    return matched_names


async def extract_candidate_news(
    page: Page,
    source_url: str,
) -> list[dict[str, str | None]]:
    selectors = ["article", ".post", ".news-item", "li", "div"]

    for selector in selectors:
        raw_candidates = await page.evaluate(
            """
            ({ selector }) => {
                            const normalize = (value) => (value || '').replace(/\\s+/g, ' ').trim();
              return Array.from(document.querySelectorAll(selector))
                .map((block) => {
                  const anchor = block.querySelector('a[href]');
                  if (!anchor) return null;

                  const href = anchor.getAttribute('href');
                  const title = normalize(anchor.textContent);
                  if (!href || !title) return null;

                  const summaryElement = block.querySelector('p');
                  const summary = normalize(summaryElement?.textContent || '');

                  return {
                    title,
                    href,
                    summary: summary || null,
                  };
                })
                .filter(Boolean);
            }
            """,
            {"selector": selector},
        )

        candidates = [
            {
                "title": item["title"],
                "url": urljoin(source_url, item["href"]),
                "summary": item["summary"],
            }
            for item in raw_candidates
        ]
        if candidates:
            return candidates

    raw_candidates = await page.evaluate("""
        () => {
                    const normalize = (value) => (value || '').replace(/\\s+/g, ' ').trim();
          return Array.from(document.querySelectorAll('a[href]'))
            .map((anchor) => {
              const href = anchor.getAttribute('href');
              const title = normalize(anchor.textContent);
              if (!href || !title) return null;

              return {
                title,
                href,
                summary: null,
              };
            })
            .filter(Boolean);
        }
        """)

    return [
        {
            "title": item["title"],
            "url": urljoin(source_url, item["href"]),
            "summary": item["summary"],
        }
        for item in raw_candidates
    ]


def is_saci_clipping_url(url: str) -> bool:
    normalized_url = url.casefold()
    return "saci.ufscar.br/servico_clipping" in normalized_url


def apply_saci_date_filters(
    url: str,
    start_date: date | None,
    end_date: date | None,
) -> str:
    if not start_date and not end_date:
        return url

    parsed_url = urlparse(url)
    query_params = dict(parse_qsl(parsed_url.query, keep_blank_values=True))

    if start_date:
        query_params["inicio"] = start_date.strftime("%d/%m/%Y")
    if end_date:
        query_params["fim"] = end_date.strftime("%d/%m/%Y")

    return urlunparse(parsed_url._replace(query=urlencode(query_params)))


def apply_saci_pagination(url: str, page_number: int) -> str:
    if page_number <= 1:
        return url

    parsed_url = urlparse(url)
    query_params = dict(parse_qsl(parsed_url.query, keep_blank_values=True))
    query_params["pag"] = str(page_number)
    return urlunparse(parsed_url._replace(query=urlencode(query_params)))


async def extract_saci_pagination_numbers(
    page: Page,
    max_listing_pages: int,
) -> list[int]:
    try:
        hrefs = await page.eval_on_selector_all(
            "a[href*='pag=']",
            "elements => elements.map((element) => element.getAttribute('href') || '')",
        )
    except Exception:
        return []

    numbers: set[int] = set()
    for href in hrefs:
        if not isinstance(href, str) or "pag=" not in href:
            continue

        try:
            page_str = dict(parse_qsl(urlparse(href).query, keep_blank_values=True)).get(
                "pag"
            )
            if not page_str:
                continue

            page_number = int(page_str)
            if 2 <= page_number <= max_listing_pages:
                numbers.add(page_number)
        except ValueError:
            continue

    return sorted(numbers)


async def try_fetch_article_text(page, url: str, timeout_ms: int) -> str:
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        article_text = await page.evaluate("""
            () => {
              const normalize = (value) => (value || '').replace(/\\s+/g, ' ').trim();
              const selectors = ['article', 'main', '.entry-content', '.post-content', '.content'];

              for (const selector of selectors) {
                const block = document.querySelector(selector);
                if (block) {
                  return normalize(block.textContent);
                }
              }

              return normalize(document.body?.textContent || '');
            }
            """)
        return article_text
    except PlaywrightTimeoutError:
        return ""
    except PlaywrightError:
        return ""


async def scrape_news(
    names: list[str],
    source_url: str,
    limit: int,
    timeout: float,
    start_date: date | None = None,
    end_date: date | None = None,
    request_delay_seconds: float = REQUEST_DELAY_SECONDS,
    max_article_fetches: int | None = None,
    max_listing_pages: int = MAX_LISTING_PAGES,
) -> list[NewsItem]:
    timeout_ms = int(timeout * 1000)
    max_fetches = max_article_fetches or max(limit * MAX_ARTICLE_FETCHES_MULTIPLIER, 20)
    name_variants = {name: build_name_variants(name) for name in names}

    results: list[NewsItem] = []
    seen: set[tuple[str, str]] = set()
    article_text_cache: dict[str, str] = {}
    article_fetch_count = 0

    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            context = await browser.new_context(
                extra_http_headers={
                    "Referer": source_url,
                    "User-Agent": "Mozilla/5.0",
                }
            )
            listing_page = await context.new_page()

            await listing_page.goto(
                source_url,
                wait_until="networkidle",
                timeout=timeout_ms,
            )
            candidates = await extract_candidate_news(listing_page, source_url)

            iframe_src = await listing_page.locator("iframe[src]").first.get_attribute(
                "src"
            )
            if isinstance(iframe_src, str) and iframe_src.strip():
                iframe_url = urljoin(source_url, iframe_src)
                iframe_url = apply_saci_date_filters(
                    iframe_url,
                    start_date=start_date,
                    end_date=end_date,
                )
                iframe_page = await context.new_page()
                try:
                    await iframe_page.goto(
                        iframe_url,
                        wait_until="domcontentloaded",
                        timeout=timeout_ms,
                    )
                    candidates.extend(
                        await extract_candidate_news(iframe_page, iframe_url)
                    )

                    page_numbers = await extract_saci_pagination_numbers(
                        iframe_page,
                        max_listing_pages=max_listing_pages,
                    )
                    for page_number in page_numbers:
                        paginated_url = apply_saci_pagination(iframe_url, page_number)
                        await iframe_page.goto(
                            paginated_url,
                            wait_until="domcontentloaded",
                            timeout=timeout_ms,
                        )
                        candidates.extend(
                            await extract_candidate_news(iframe_page, paginated_url)
                        )
                        if request_delay_seconds > 0:
                            await asyncio.sleep(request_delay_seconds)
                finally:
                    await iframe_page.close()

            if any(
                is_saci_clipping_url((item.get("url") or "")) for item in candidates
            ):
                candidates = [
                    item
                    for item in candidates
                    if is_saci_clipping_url((item.get("url") or ""))
                ]

            article_page = await context.new_page()
            try:
                for candidate in candidates:
                    title = (candidate["title"] or "").strip()
                    url = (candidate["url"] or "").strip()

                    if not title or not url:
                        continue

                    dedupe_key = (title, url)
                    if dedupe_key in seen:
                        continue
                    seen.add(dedupe_key)

                    searchable_text = f"{title} {candidate['summary'] or ''}"
                    matched_names = match_names_in_text(
                        names=names,
                        searchable_text=searchable_text,
                        name_variants=name_variants,
                    )

                    if not matched_names and article_fetch_count < max_fetches:
                        article_text = article_text_cache.get(url)
                        if article_text is None:
                            article_text = await try_fetch_article_text(
                                article_page,
                                url,
                                timeout_ms,
                            )
                            article_text_cache[url] = article_text
                            article_fetch_count += 1
                            if request_delay_seconds > 0:
                                await asyncio.sleep(request_delay_seconds)

                        if article_text:
                            searchable_text = (
                                f"{title} {candidate['summary'] or ''} {article_text}"
                            )
                            matched_names = match_names_in_text(
                                names=names,
                                searchable_text=searchable_text,
                                name_variants=name_variants,
                            )

                    if not matched_names:
                        continue

                    results.append(
                        NewsItem(
                            title=title,
                            url=url,
                            summary=candidate["summary"],
                            matched_names=matched_names,
                        )
                    )

                    if len(results) >= limit:
                        break
            finally:
                await article_page.close()
                await listing_page.close()
                await context.close()
                await browser.close()
    except PlaywrightTimeoutError as error:
        raise RuntimeError(f"Tempo limite ao acessar {source_url}") from error
    except PlaywrightError as error:
        raise RuntimeError(f"Falha ao acessar fonte: {error}") from error

    return results
