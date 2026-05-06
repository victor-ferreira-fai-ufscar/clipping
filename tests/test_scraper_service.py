from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from types import SimpleNamespace

import pytest

import app.services.scraper as scraper_module


@dataclass
class FakeLocator:
    src: str | None

    @property
    def first(self) -> "FakeLocator":
        return self

    async def get_attribute(self, _name: str) -> str | None:
        return self.src


class FakePage:
    def __init__(self, iframe_src: str | None = None):
        self._iframe_src = iframe_src
        self.goto_calls: list[str] = []

    async def goto(self, url: str, **_kwargs) -> None:
        self.goto_calls.append(url)

    def locator(self, _selector: str) -> FakeLocator:
        return FakeLocator(self._iframe_src)

    async def close(self) -> None:
        return None


class FakeContext:
    def __init__(self, pages: list[FakePage]):
        self._pages = pages

    async def new_page(self) -> FakePage:
        return self._pages.pop(0)

    async def close(self) -> None:
        return None


class FakeBrowser:
    def __init__(self, context: FakeContext):
        self._context = context

    async def new_context(self, **_kwargs) -> FakeContext:
        return self._context

    async def close(self) -> None:
        return None


class FakeChromium:
    def __init__(self, browser: FakeBrowser):
        self._browser = browser

    async def launch(self, **_kwargs) -> FakeBrowser:
        return self._browser


class FakePlaywrightManager:
    def __init__(self, browser: FakeBrowser):
        self._playwright = SimpleNamespace(chromium=FakeChromium(browser))

    async def __aenter__(self):
        return self._playwright

    async def __aexit__(self, _exc_type, _exc, _tb):
        return None


def test_apply_saci_date_filters_adds_dates_to_query() -> None:
    base_url = "https://www.saci.ufscar.br/servico_clippings?uni=1"

    result = scraper_module.apply_saci_date_filters(
        base_url,
        start_date=date(2026, 5, 1),
        end_date=date(2026, 5, 6),
    )

    assert "uni=1" in result
    assert "inicio=01%2F05%2F2026" in result
    assert "fim=06%2F05%2F2026" in result


def test_apply_saci_pagination_adds_page_parameter() -> None:
    base_url = "https://www.saci.ufscar.br/servico_clippings?uni=1"

    result = scraper_module.apply_saci_pagination(base_url, 3)

    assert "uni=1" in result
    assert "pag=3" in result


def test_build_name_variants_includes_abbreviation_forms() -> None:
    variants = scraper_module.build_name_variants("Heber Lombardi de Carvalho")

    assert "heber lombardi de carvalho" in variants
    assert "heber carvalho" in variants
    assert "h l carvalho" in variants
    assert "h carvalho" not in variants


@pytest.mark.asyncio
async def test_scrape_news_matches_name_in_title(monkeypatch) -> None:
    listing_page = FakePage(iframe_src=None)
    article_page = FakePage(iframe_src=None)

    context = FakeContext([listing_page, article_page])
    browser = FakeBrowser(context)

    monkeypatch.setattr(
        scraper_module,
        "async_playwright",
        lambda: FakePlaywrightManager(browser),
    )

    async def fake_extract_candidate_news(_page, _source_url: str):
        return [
            {
                "title": "Cátedra Sistemas Complexos e suas Complexidades realiza primeira oficina",
                "url": "https://www.saci.ufscar.br/servico_clipping?id=82653",
                "summary": None,
            }
        ]

    monkeypatch.setattr(
        scraper_module, "extract_candidate_news", fake_extract_candidate_news
    )

    results = await scraper_module.scrape_news(
        names=["Cátedra Sistemas Complexos e suas Complexidades"],
        source_url="https://www.ccs.ufscar.br/clipping",
        limit=10,
        timeout=20.0,
        request_delay_seconds=0,
    )

    assert len(results) == 1
    assert results[0].matched_names == [
        "Cátedra Sistemas Complexos e suas Complexidades"
    ]


@pytest.mark.asyncio
async def test_scrape_news_uses_article_text_when_title_has_no_match(
    monkeypatch,
) -> None:
    listing_page = FakePage(iframe_src=None)
    article_page = FakePage(iframe_src=None)

    context = FakeContext([listing_page, article_page])
    browser = FakeBrowser(context)

    monkeypatch.setattr(
        scraper_module,
        "async_playwright",
        lambda: FakePlaywrightManager(browser),
    )

    async def fake_extract_candidate_news(_page, _source_url: str):
        return [
            {
                "title": "Noticia generica",
                "url": "https://www.saci.ufscar.br/servico_clipping?id=999",
                "summary": None,
            }
        ]

    async def fake_fetch_article_text(_page, _url: str, _timeout_ms: int) -> str:
        return "Texto completo com Heber Lombardi de Carvalho na materia."

    monkeypatch.setattr(
        scraper_module, "extract_candidate_news", fake_extract_candidate_news
    )
    monkeypatch.setattr(
        scraper_module, "try_fetch_article_text", fake_fetch_article_text
    )

    results = await scraper_module.scrape_news(
        names=["Heber Lombardi de Carvalho"],
        source_url="https://www.ccs.ufscar.br/clipping",
        limit=10,
        timeout=20.0,
        request_delay_seconds=0,
    )

    assert len(results) == 1
    assert results[0].matched_names == ["Heber Lombardi de Carvalho"]


@pytest.mark.asyncio
async def test_scrape_news_applies_date_filter_to_iframe_url(monkeypatch) -> None:
    listing_page = FakePage(
        iframe_src="https://www.saci.ufscar.br/servico_clippings?uni=1"
    )
    iframe_page = FakePage(iframe_src=None)
    article_page = FakePage(iframe_src=None)

    context = FakeContext([listing_page, iframe_page, article_page])
    browser = FakeBrowser(context)

    monkeypatch.setattr(
        scraper_module,
        "async_playwright",
        lambda: FakePlaywrightManager(browser),
    )

    async def fake_extract_candidate_news(_page, source_url: str):
        if "servico_clippings" in source_url:
            return [
                {
                    "title": "Noticia do clipping",
                    "url": "https://www.saci.ufscar.br/servico_clipping?id=123",
                    "summary": None,
                }
            ]
        return []

    monkeypatch.setattr(
        scraper_module, "extract_candidate_news", fake_extract_candidate_news
    )

    await scraper_module.scrape_news(
        names=["Noticia do clipping"],
        source_url="https://www.ccs.ufscar.br/clipping",
        limit=10,
        timeout=20.0,
        start_date=date(2026, 5, 1),
        end_date=date(2026, 5, 6),
        request_delay_seconds=0,
        max_listing_pages=1,
    )

    assert len(iframe_page.goto_calls) == 1
    assert "inicio=01%2F05%2F2026" in iframe_page.goto_calls[0]
    assert "fim=06%2F05%2F2026" in iframe_page.goto_calls[0]


@pytest.mark.asyncio
async def test_scrape_news_matches_abbreviation_in_article_title(monkeypatch) -> None:
    listing_page = FakePage(iframe_src=None)
    article_page = FakePage(iframe_src=None)

    context = FakeContext([listing_page, article_page])
    browser = FakeBrowser(context)

    monkeypatch.setattr(
        scraper_module,
        "async_playwright",
        lambda: FakePlaywrightManager(browser),
    )

    async def fake_extract_candidate_news(_page, _source_url: str):
        return [
            {
                "title": "H. L. Carvalho participa de evento internacional",
                "url": "https://www.saci.ufscar.br/servico_clipping?id=777",
                "summary": None,
            }
        ]

    monkeypatch.setattr(
        scraper_module, "extract_candidate_news", fake_extract_candidate_news
    )

    results = await scraper_module.scrape_news(
        names=["Heber Lombardi de Carvalho"],
        source_url="https://www.ccs.ufscar.br/clipping",
        limit=10,
        timeout=20.0,
        request_delay_seconds=0,
    )

    assert len(results) == 1
    assert results[0].matched_names == ["Heber Lombardi de Carvalho"]


@pytest.mark.asyncio
async def test_scrape_news_respects_max_article_fetches(monkeypatch) -> None:
    listing_page = FakePage(iframe_src=None)
    article_page = FakePage(iframe_src=None)

    context = FakeContext([listing_page, article_page])
    browser = FakeBrowser(context)

    monkeypatch.setattr(
        scraper_module,
        "async_playwright",
        lambda: FakePlaywrightManager(browser),
    )

    async def fake_extract_candidate_news(_page, _source_url: str):
        return [
            {
                "title": "Noticia sem nome 1",
                "url": "https://www.saci.ufscar.br/servico_clipping?id=1",
                "summary": None,
            },
            {
                "title": "Noticia sem nome 2",
                "url": "https://www.saci.ufscar.br/servico_clipping?id=2",
                "summary": None,
            },
        ]

    fetch_calls = {"count": 0}

    async def fake_fetch_article_text(_page, _url: str, _timeout_ms: int) -> str:
        fetch_calls["count"] += 1
        return ""

    monkeypatch.setattr(
        scraper_module, "extract_candidate_news", fake_extract_candidate_news
    )
    monkeypatch.setattr(
        scraper_module, "try_fetch_article_text", fake_fetch_article_text
    )

    results = await scraper_module.scrape_news(
        names=["Heber Lombardi de Carvalho"],
        source_url="https://www.ccs.ufscar.br/clipping",
        limit=10,
        timeout=20.0,
        request_delay_seconds=0,
        max_article_fetches=1,
    )

    assert results == []
    assert fetch_calls["count"] == 1


@pytest.mark.asyncio
async def test_scrape_news_navigates_across_pagination(monkeypatch) -> None:
    listing_page = FakePage(
        iframe_src="https://www.saci.ufscar.br/servico_clippings?uni=1"
    )
    iframe_page = FakePage(iframe_src=None)
    article_page = FakePage(iframe_src=None)

    context = FakeContext([listing_page, iframe_page, article_page])
    browser = FakeBrowser(context)

    monkeypatch.setattr(
        scraper_module,
        "async_playwright",
        lambda: FakePlaywrightManager(browser),
    )

    async def fake_extract_candidate_news(_page, source_url: str):
        if "pag=2" in source_url:
            return [
                {
                    "title": "Noticia pag 2",
                    "url": "https://www.saci.ufscar.br/servico_clipping?id=2",
                    "summary": None,
                }
            ]
        if "pag=3" in source_url:
            return [
                {
                    "title": "Noticia pag 3",
                    "url": "https://www.saci.ufscar.br/servico_clipping?id=3",
                    "summary": None,
                }
            ]
        # page 4+ returns empty → early stop
        if "pag=" in source_url:
            return []
        return []

    monkeypatch.setattr(
        scraper_module, "extract_candidate_news", fake_extract_candidate_news
    )

    results = await scraper_module.scrape_news(
        names=["Noticia"],
        source_url="https://www.ccs.ufscar.br/clipping",
        limit=10,
        timeout=20.0,
        request_delay_seconds=0,
        max_listing_pages=10,
        max_article_fetches=0,
    )

    assert "pag=2" in iframe_page.goto_calls[1]
    assert "pag=3" in iframe_page.goto_calls[2]
    # stopped at pag=4 (empty), so only 3 iframe.goto calls: pag=1, pag=2, pag=3, pag=4(empty stop)
    assert len(iframe_page.goto_calls) == 4
    assert len(results) == 2
