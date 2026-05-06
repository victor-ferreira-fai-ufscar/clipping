# Clipping

API de scraping para cruzar noticias do clipping da UFSCar com uma lista de nomes de docentes.

Fonte principal usada neste inicio:

- [Clipping UFSCar](https://www.ccs.ufscar.br/clipping)

Lista inicial de nomes:

- [Lista de nomes](./assets/nomes.csv)

## Stack

- Python + `uv`
- FastAPI
- Playwright
- Docker Compose (fluxo recomendado)

## MCPs no VS Code (Playwright e Context7)

Este repositorio inclui configuracao local em `.vscode/mcp.json` com dois servidores:

- `playwright` via `@playwright/mcp`
- `context7` via `@upstash/context7-mcp`

Pre-requisitos no host:

- Node.js 18+
- `npx` disponivel

Passos:

1. Abra o projeto no VS Code.
2. Confirme que o arquivo `.vscode/mcp.json` esta presente.
3. Reinicie a janela do VS Code (`Developer: Reload Window`) para carregar os MCPs.

Opcional (Context7 com pesquisa aprofundada):

- Defina `CONTEXT7_API_KEY` no ambiente do VS Code para habilitar `researchMode`.
- Sem essa chave, o Context7 ainda funciona no modo padrao.

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

Se `names` nao for enviado no corpo, o endpoint usa automaticamente o arquivo `assets/nomes.csv`.
