from fastapi import Body, FastAPI, HTTPException
from scalar_fastapi import get_scalar_api_reference

from app.core.settings import settings
from app.schemas import ScrapeRequest, ScrapeResponse
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
            "defaultFile": {
                "summary": "Usar arquivo padrao de nomes",
                "description": "Envia um corpo vazio para usar automaticamente o arquivo `assets/nomes.csv`.",
                "value": {},
            },
        },
    ),
) -> ScrapeResponse:
    request = request or ScrapeRequest()
    names = request.names or load_names(settings.names_file)
    source_url = request.source_url or settings.clipping_url
    limit = request.limit or settings.default_limit

    try:
        items = await scrape_news(
            names=names,
            source_url=source_url,
            limit=limit,
            timeout=settings.request_timeout,
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
