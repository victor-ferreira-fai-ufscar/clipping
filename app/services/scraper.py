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

            title = anchor.get_text(" ", strip=True)
            if not title:
                continue

            summary_tag = block.select_one("p")
            summary = summary_tag.get_text(" ", strip=True) if summary_tag else None

            candidates.append(
                {
                    "title": title,
                    "url": urljoin(source_url, anchor["href"]),
                    "summary": summary,
                }
            )

        if candidates:
            break

    if candidates:
        return candidates

    for anchor in soup.select("a[href]"):
        title = anchor.get_text(" ", strip=True)
        if not title:
            continue

        candidates.append(
            {
                "title": title,
                "url": urljoin(source_url, anchor["href"]),
                "summary": None,
            }
        )

    return candidates


async def scrape_news(
    names: list[str],
    source_url: str,
    limit: int,
    timeout: float,
) -> list[NewsItem]:
    timeout_ms = int(timeout * 1000)

    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(source_url, wait_until="networkidle", timeout=timeout_ms)
            html_content = await page.content()
            await browser.close()
    except PlaywrightTimeoutError as error:
        raise RuntimeError(f"Tempo limite ao acessar {source_url}") from error
    except PlaywrightError as error:
        raise RuntimeError(f"Falha ao acessar fonte: {error}") from error

    soup = BeautifulSoup(html_content, "html.parser")
    candidates = extract_candidate_news(soup, source_url)

    normalized_names = {name: normalize_text(name) for name in names}

    results: list[NewsItem] = []
    seen: set[tuple[str, str]] = set()

    for candidate in candidates:
        title = (candidate["title"] or "").strip()
        url = (candidate["url"] or "").strip()

        if not title or not url:
            continue

        dedupe_key = (title, url)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        searchable_text = normalize_text(f"{title} {candidate['summary'] or ''}")
        matched_names = [
            original_name
            for original_name, normalized_name in normalized_names.items()
            if normalized_name and normalized_name in searchable_text
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

    return results
