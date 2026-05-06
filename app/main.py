from datetime import date

from fastapi import Body, FastAPI, HTTPException
from scalar_fastapi import get_scalar_api_reference

from app.core.settings import settings
from app.schemas import (
    PersonMatchCount,
    ScrapeAggregateResponse,
    ScrapeRequest,
    ScrapeResponse,
)
from app.services.names_loader import load_names
from app.services.scraper import scrape_news

app = FastAPI(
    title=settings.app_name,
    summary="API para buscar noticias do clipping da UFSCar e cruzar com nomes de interesse.",
    description=(
        "Use `name` para consultar uma unica pessoa, `names` para consultar varias, "
        "ou envie um corpo vazio para usar automaticamente o arquivo `assets/nomes.csv`."
    ),
    docs_url=None,
    redoc_url=None,
    openapi_tags=[
        {
            "name": "Infra",
            "description": "Endpoints de observabilidade e disponibilidade da API.",
        },
        {
            "name": "Clipping",
            "description": "Consulta noticias do clipping da CCS UFSCar e cruza os resultados com nomes informados no request.",
        },
    ],
)


@app.get(
    "/scalar",
    include_in_schema=False,
)
async def scalar_reference():
    return get_scalar_api_reference(
        openapi_url=app.openapi_url,
        title=f"{settings.app_name} - Referencia da API",
    )


@app.get(
    "/health",
    tags=["Infra"],
    summary="Verifica disponibilidade da API",
    description="Endpoint simples para confirmar que a aplicacao esta no ar e pronta para receber requisicoes.",
)
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


def resolve_scrape_parameters(
    request: ScrapeRequest | None,
) -> tuple[list[str], str, int, date | None, date | None]:
    parsed_request = request or ScrapeRequest()
    names = parsed_request.names or load_names(settings.names_file)
    source_url = parsed_request.source_url or settings.clipping_url
    limit = parsed_request.limit or settings.default_limit
    return names, source_url, limit, parsed_request.start_date, parsed_request.end_date


@app.post(
    "/scrape",
    response_model=ScrapeResponse,
    tags=["Clipping"],
    summary="Busca noticias do clipping por nome",
    description=(
        "Aceita um unico nome em `name`, uma lista em `names`, ou um corpo vazio para usar os nomes padrao de `assets/nomes.csv`. "
        "Quando `name` e `names` sao enviados juntos, o nome individual e incorporado a lista final antes da busca."
    ),
    response_description="Noticias encontradas no clipping com os nomes identificados no titulo, resumo ou conteudo da noticia.",
)
async def run_scrape(
    request: ScrapeRequest | None = Body(
        default=None,
        openapi_examples={
            "singleName": {
                "summary": "Buscar por uma unica pessoa",
                "description": "Usa o campo `name` para encontrar noticias relacionadas a uma pessoa especifica.",
                "value": {
                    "name": "Heber Lombardi de Carvalho",
                    "limit": 10,
                },
            },
            "multipleNames": {
                "summary": "Buscar por varios nomes",
                "description": "Usa o campo `names` para cruzar varias pessoas em uma unica execucao.",
                "value": {
                    "names": [
                        "Heber Lombardi de Carvalho",
                        "Alexandra Sanches",
                    ],
                    "limit": 20,
                    "source_url": "https://www.ccs.ufscar.br/clipping",
                },
            },
            "dateRange": {
                "summary": "Buscar por periodo",
                "description": "Filtra noticias entre `start_date` e `end_date`.",
                "value": {
                    "name": "Heber Lombardi de Carvalho",
                    "start_date": "2026-05-01",
                    "end_date": "2026-05-06",
                },
            },
            "defaultFile": {
                "summary": "Usar arquivo padrao de nomes",
                "description": "Envia um corpo vazio para usar automaticamente o arquivo `assets/nomes.csv`.",
                "value": {},
            },
        },
    ),
) -> ScrapeResponse:
    names, source_url, limit, start_date, end_date = resolve_scrape_parameters(request)

    try:
        items = await scrape_news(
            names=names,
            source_url=source_url,
            limit=limit,
            timeout=settings.request_timeout,
            start_date=start_date,
            end_date=end_date,
            request_delay_seconds=settings.request_delay_seconds,
            max_article_fetches=settings.max_article_fetches,
            max_listing_pages=settings.max_listing_pages,
        )
    except FileNotFoundError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error

    return ScrapeResponse(
        source_url=source_url,
        total_collected=len(items),
        total_matched=len(items),
        items=items,
    )


@app.post(
    "/scrape/aggregate",
    response_model=ScrapeAggregateResponse,
    tags=["Clipping"],
    summary="Agrega noticias por pessoa",
    description=(
        "Usa o mesmo payload de `/scrape` e retorna a quantidade de noticias por pessoa encontrada no clipping."
    ),
    response_description="Resumo agregado de noticias por nome.",
)
async def run_scrape_aggregate(
    request: ScrapeRequest | None = Body(default=None),
) -> ScrapeAggregateResponse:
    names, source_url, limit, start_date, end_date = resolve_scrape_parameters(request)

    try:
        items = await scrape_news(
            names=names,
            source_url=source_url,
            limit=limit,
            timeout=settings.request_timeout,
            start_date=start_date,
            end_date=end_date,
            request_delay_seconds=settings.request_delay_seconds,
            max_article_fetches=settings.max_article_fetches,
            max_listing_pages=settings.max_listing_pages,
        )
    except FileNotFoundError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error

    counts: dict[str, int] = {name: 0 for name in names}

    for item in items:
        for matched_name in set(item.matched_names):
            if matched_name not in counts:
                counts[matched_name] = 0
            counts[matched_name] += 1

    people = [
        PersonMatchCount(name=name, news_count=news_count)
        for name, news_count in sorted(
            counts.items(), key=lambda value: (-value[1], value[0])
        )
    ]

    return ScrapeAggregateResponse(
        source_url=source_url,
        total_news=len(items),
        total_people_matched=sum(1 for person in people if person.news_count > 0),
        people=people,
    )
