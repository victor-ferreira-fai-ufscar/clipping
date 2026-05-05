from datetime import datetime

from pydantic import BaseModel, Field


class NewsItem(BaseModel):
    title: str
    url: str
    summary: str | None = None
    published_at: datetime | None = None
    matched_names: list[str] = Field(default_factory=list)


class ScrapeRequest(BaseModel):
    names: list[str] | None = None
    limit: int | None = Field(default=None, ge=1, le=500)
    source_url: str | None = None


class ScrapeResponse(BaseModel):
    source_url: str
    total_collected: int
    total_matched: int
    items: list[NewsItem]
