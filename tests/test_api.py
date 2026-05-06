from datetime import date
from pathlib import Path
import sys
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.main as main_module
from app.schemas import NewsItem

client = TestClient(main_module.app)


def test_healthcheck_returns_ok() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_scalar_route_serves_api_reference() -> None:
    response = client.get("/scalar")

    assert response.status_code == 200
    assert "Scalar" in response.text
    assert "/openapi.json" in response.text


def test_scrape_accepts_single_name(monkeypatch) -> None:
    fake_scrape = AsyncMock(return_value=[])
    monkeypatch.setattr(main_module, "scrape_news", fake_scrape)
    monkeypatch.setattr(
        main_module,
        "load_names",
        lambda _: (_ for _ in ()).throw(
            AssertionError("load_names nao deveria ser chamado")
        ),
    )

    response = client.post(
        "/scrape",
        json={
            "name": "  Heber Lombardi de Carvalho  ",
            "limit": 10,
        },
    )

    assert response.status_code == 200
    fake_scrape.assert_awaited_once_with(
        names=["Heber Lombardi de Carvalho"],
        source_url=main_module.settings.clipping_url,
        limit=10,
        timeout=main_module.settings.request_timeout,
        start_date=None,
        end_date=None,
        request_delay_seconds=main_module.settings.request_delay_seconds,
        max_article_fetches=main_module.settings.max_article_fetches,
        max_listing_pages=main_module.settings.max_listing_pages,
    )


def test_scrape_accepts_name_and_names(monkeypatch) -> None:
    fake_scrape = AsyncMock(return_value=[])
    monkeypatch.setattr(main_module, "scrape_news", fake_scrape)

    response = client.post(
        "/scrape",
        json={
            "name": "Heber Lombardi de Carvalho",
            "names": [
                "Alexandra Sanches",
                "Heber Lombardi de Carvalho",
                "  Alexandra Sanches  ",
            ],
        },
    )

    assert response.status_code == 200
    fake_scrape.assert_awaited_once_with(
        names=["Heber Lombardi de Carvalho", "Alexandra Sanches"],
        source_url=main_module.settings.clipping_url,
        limit=main_module.settings.default_limit,
        timeout=main_module.settings.request_timeout,
        start_date=None,
        end_date=None,
        request_delay_seconds=main_module.settings.request_delay_seconds,
        max_article_fetches=main_module.settings.max_article_fetches,
        max_listing_pages=main_module.settings.max_listing_pages,
    )


def test_scrape_uses_default_file_when_body_is_empty(monkeypatch) -> None:
    fake_scrape = AsyncMock(return_value=[])
    monkeypatch.setattr(main_module, "scrape_news", fake_scrape)
    monkeypatch.setattr(main_module, "load_names", lambda _: ["Nome Padrao"])

    response = client.post("/scrape", json={})

    assert response.status_code == 200
    fake_scrape.assert_awaited_once_with(
        names=["Nome Padrao"],
        source_url=main_module.settings.clipping_url,
        limit=main_module.settings.default_limit,
        timeout=main_module.settings.request_timeout,
        start_date=None,
        end_date=None,
        request_delay_seconds=main_module.settings.request_delay_seconds,
        max_article_fetches=main_module.settings.max_article_fetches,
        max_listing_pages=main_module.settings.max_listing_pages,
    )


def test_scrape_aggregate_counts_news_by_person(monkeypatch) -> None:
    fake_items = [
        NewsItem(
            title="Noticia 1",
            url="https://example.com/1",
            matched_names=["Heber Lombardi de Carvalho", "Alexandra Sanches"],
        ),
        NewsItem(
            title="Noticia 2",
            url="https://example.com/2",
            matched_names=["Heber Lombardi de Carvalho"],
        ),
    ]

    fake_scrape = AsyncMock(return_value=fake_items)
    monkeypatch.setattr(main_module, "scrape_news", fake_scrape)

    response = client.post(
        "/scrape/aggregate",
        json={"names": ["Heber Lombardi de Carvalho", "Alexandra Sanches"]},
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["total_news"] == 2
    assert payload["total_people_matched"] == 2
    assert payload["people"] == [
        {"name": "Heber Lombardi de Carvalho", "news_count": 2},
        {"name": "Alexandra Sanches", "news_count": 1},
    ]


def test_scrape_accepts_date_range(monkeypatch) -> None:
    fake_scrape = AsyncMock(return_value=[])
    monkeypatch.setattr(main_module, "scrape_news", fake_scrape)

    response = client.post(
        "/scrape",
        json={
            "name": "Heber Lombardi de Carvalho",
            "start_date": "2026-05-01",
            "end_date": "2026-05-06",
        },
    )

    assert response.status_code == 200
    fake_scrape.assert_awaited_once_with(
        names=["Heber Lombardi de Carvalho"],
        source_url=main_module.settings.clipping_url,
        limit=main_module.settings.default_limit,
        timeout=main_module.settings.request_timeout,
        start_date=date(2026, 5, 1),
        end_date=date(2026, 5, 6),
        request_delay_seconds=main_module.settings.request_delay_seconds,
        max_article_fetches=main_module.settings.max_article_fetches,
        max_listing_pages=main_module.settings.max_listing_pages,
    )


def test_scrape_rejects_invalid_date_range() -> None:
    response = client.post(
        "/scrape",
        json={
            "name": "Heber Lombardi de Carvalho",
            "start_date": "2026-05-10",
            "end_date": "2026-05-01",
        },
    )

    assert response.status_code == 422


def test_openapi_documents_name_modes_and_examples() -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200

    payload = response.json()
    scrape_schema = payload["components"]["schemas"]["ScrapeRequest"]
    scrape_operation = payload["paths"]["/scrape"]["post"]

    assert "name" in scrape_schema["properties"]
    assert "names" in scrape_schema["properties"]
    assert "nome unico" in scrape_schema["properties"]["name"]["description"].casefold()
    assert (
        "singleName"
        in scrape_operation["requestBody"]["content"]["application/json"]["examples"]
    )
    assert (
        "multipleNames"
        in scrape_operation["requestBody"]["content"]["application/json"]["examples"]
    )
    assert (
        "defaultFile"
        in scrape_operation["requestBody"]["content"]["application/json"]["examples"]
    )
    assert "start_date" in scrape_schema["properties"]
    assert "end_date" in scrape_schema["properties"]
    assert (
        "dateRange"
        in scrape_operation["requestBody"]["content"]["application/json"]["examples"]
    )
    assert "/scrape/aggregate" in payload["paths"]
