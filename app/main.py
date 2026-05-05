from fastapi import FastAPI, HTTPException

from app.core.settings import settings
from app.schemas import ScrapeRequest, ScrapeResponse
from app.services.names_loader import load_names
from app.services.scraper import scrape_news

app = FastAPI(title=settings.app_name)


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/scrape", response_model=ScrapeResponse)
async def run_scrape(request: ScrapeRequest) -> ScrapeResponse:
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
