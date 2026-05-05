# Clipping

API de scraping para cruzar noticias do clipping da UFSCar com uma lista de nomes de docentes.

Fonte principal usada neste inicio:

- [Clipping UFSCar](https://www.ccs.ufscar.br/clipping)

Lista inicial de nomes:

- [50 nomes de docentes](./docs/50-nomes-docentes.csv)

## Stack

- Python + `uv`
- FastAPI
- Playwright + BeautifulSoup
- Docker Compose (fluxo recomendado)

## Como rodar (recomendado: Docker Compose)

```bash
docker compose up --build
```

API disponivel em:

- `http://localhost:8000`
- Swagger: `http://localhost:8000/docs`

## Como rodar localmente com UV

```bash
uv venv
source .venv/bin/activate
uv sync
uv run playwright install chromium
uv run uvicorn app.main:app --reload
```

## Endpoints iniciais

- `GET /health`
- `POST /scrape`

Exemplo de request:

```bash
curl -X POST "http://localhost:8000/scrape" \
 -H "Content-Type: application/json" \
 -d '{
  "limit": 20,
  "source_url": "https://www.ccs.ufscar.br/clipping"
 }'
```

Se `names` nao for enviado no corpo, o endpoint usa automaticamente o arquivo `docs/50-nomes-docentes.csv`.
