from __future__ import annotations

import unicodedata
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

from app.schemas import NewsItem


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    without_accents = "".join(
        char for char in normalized if not unicodedata.combining(char)
    )
    return without_accents.casefold().strip()


def extract_candidate_news(
    soup: BeautifulSoup, source_url: str
) -> list[dict[str, str | None]]:
    candidates: list[dict[str, str | None]] = []

    selectors = ["article", ".post", ".news-item", "li", "div"]

    for selector in selectors:
        for block in soup.select(selector):
            anchor = block.select_one("a[href]")
            if not anchor:
                continue

            href = anchor.get("href")
            if not isinstance(href, str) or not href.strip():
                continue

            title = anchor.get_text(" ", strip=True)
            if not title:
                continue

            summary_tag = block.select_one("p")
            summary = summary_tag.get_text(" ", strip=True) if summary_tag else None

            candidates.append(
                {
                    "title": title,
                    "url": urljoin(source_url, href),
                    "summary": summary,
                }
            )

        if candidates:
            break

    if candidates:
        return candidates

    for anchor in soup.select("a[href]"):
        href = anchor.get("href")
        if not isinstance(href, str) or not href.strip():
            continue

        title = anchor.get_text(" ", strip=True)
        if not title:
            continue

        candidates.append(
            {
                "title": title,
                "url": urljoin(source_url, href),
                "summary": None,
            }
        )

    return candidates


def extract_article_text(html_content: str) -> str:
    soup = BeautifulSoup(html_content, "html.parser")

    content_selectors = [
        "article",
        "main",
        ".entry-content",
        ".post-content",
        ".content",
    ]

    for selector in content_selectors:
        block = soup.select_one(selector)
        if block:
            return block.get_text(" ", strip=True)

    return soup.get_text(" ", strip=True)


def is_saci_clipping_url(url: str) -> bool:
    normalized_url = url.casefold()
    return "saci.ufscar.br/servico_clipping" in normalized_url


async def try_fetch_article_text(page, url: str, timeout_ms: int) -> str:
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        html_content = await page.content()
        return extract_article_text(html_content)
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
            html_content = await listing_page.content()

            soup = BeautifulSoup(html_content, "html.parser")
            candidates = extract_candidate_news(soup, source_url)

            iframe = soup.select_one("iframe[src]")
            iframe_src = iframe.get("src") if iframe else None
            if isinstance(iframe_src, str) and iframe_src.strip():
                iframe_url = urljoin(source_url, iframe_src)
                iframe_page = await context.new_page()
                try:
                    await iframe_page.goto(
                        iframe_url,
                        wait_until="domcontentloaded",
                        timeout=timeout_ms,
                    )
                    iframe_html = await iframe_page.content()
                    iframe_soup = BeautifulSoup(iframe_html, "html.parser")
                    candidates.extend(extract_candidate_news(iframe_soup, iframe_url))
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
