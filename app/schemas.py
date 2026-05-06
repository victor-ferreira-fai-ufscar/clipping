from datetime import datetime
from typing import Self

from pydantic import BaseModel, Field, model_validator


class NewsItem(BaseModel):
    title: str
    url: str
    summary: str | None = None
    published_at: datetime | None = None
    matched_names: list[str] = Field(default_factory=list)


class ScrapeRequest(BaseModel):
    name: str | None = Field(
        default=None,
        description="Nome unico para cruzar com as noticias do clipping.",
        examples=["Heber Lombardi de Carvalho"],
    )
    names: list[str] | None = Field(
        default=None,
        description="Lista de nomes para cruzar com as noticias. Se `name` tambem for enviado, ele sera somado a esta lista.",
        examples=[["Heber Lombardi de Carvalho", "Alexandra Sanches"]],
    )
    limit: int | None = Field(
        default=None,
        ge=1,
        le=500,
        description="Quantidade maxima de noticias retornadas pela API.",
        examples=[20],
    )
    source_url: str | None = Field(
        default=None,
        description="URL da pagina inicial do clipping. Se omitida, usa a URL padrao configurada da CCS UFSCar.",
        examples=["https://www.ccs.ufscar.br/clipping"],
    )

    @model_validator(mode="after")
    def normalize_names(self) -> Self:
        normalized_single = (
            self.name.strip() if self.name and self.name.strip() else None
        )
        normalized_list = [
            value.strip() for value in (self.names or []) if value and value.strip()
        ]

        merged_names: list[str] = []

        if normalized_single:
            merged_names.append(normalized_single)

        for value in normalized_list:
            if value not in merged_names:
                merged_names.append(value)

        self.name = normalized_single
        self.names = merged_names or None
        return self


class ScrapeResponse(BaseModel):
    source_url: str
    total_collected: int
    total_matched: int
    items: list[NewsItem]


class PersonMatchCount(BaseModel):
    name: str
    news_count: int


class ScrapeAggregateResponse(BaseModel):
    source_url: str
    total_news: int
    total_people_matched: int
    people: list[PersonMatchCount]
