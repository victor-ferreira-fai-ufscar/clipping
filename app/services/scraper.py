from __future__ import annotations

import unicodedata
from urllib.parse import urljoin

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

from app.schemas import NewsItem


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    without_accents = "".join(
        char for char in normalized if not unicodedata.combining(char)
    )
    return without_accents.casefold().strip()


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
) -> list[NewsItem]:
    timeout_ms = int(timeout * 1000)

    normalized_names = {name: normalize_text(name) for name in names}

    results: list[NewsItem] = []
    seen: set[tuple[str, str]] = set()

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

                    searchable_text = normalize_text(
                        f"{title} {candidate['summary'] or ''}"
                    )
                    matched_names = [
                        original_name
                        for original_name, normalized_name in normalized_names.items()
                        if normalized_name and normalized_name in searchable_text
                    ]

                    if not matched_names:
                        article_text = await try_fetch_article_text(
                            article_page,
                            url,
                            timeout_ms,
                        )
                        if article_text:
                            searchable_text = normalize_text(
                                f"{title} {candidate['summary'] or ''} {article_text}"
                            )
                            matched_names = [
                                original_name
                                for original_name, normalized_name in normalized_names.items()
                                if normalized_name
                                and normalized_name in searchable_text
                            ]

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
