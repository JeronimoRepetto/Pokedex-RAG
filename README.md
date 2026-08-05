# Pokédex AI — Multimodal RAG Lab

Unofficial, educational project: a Pokédex you can search by text or image, backed by
Retrieval-Augmented Generation over Gen-1 Pokémon data.

- **API**: FastAPI (OpenAPI docs at `/docs`)
- **Retrieval**: PostgreSQL + pgvector — multimodal embeddings + full-text search, fused with RRF
- **Orchestration**: LangGraph
- **Observability**: Langfuse

## Quickstart

```bash
cp .env.example .env   # fill in your values
docker compose up -d
```

Each component's README covers how to run, test and deploy it.

## Components

| Component | Kind | Purpose |
|---|---|---|
| `apps/data-pipeline` | job | Ingest PokéAPI data, build documents, generate embeddings |
| `apps/api` | service | Pokédex + search + RAG chat API |
| `apps/evals` | job | Golden-dataset evaluation runner |
| `libs/*` | libraries | Shared config/logging/contracts, DB models, embedders, LLM gateway |

## Disclaimer

Educational, non-commercial project built to experiment with RAG, multimodal search and
model evaluation. Not affiliated with, sponsored or endorsed by Nintendo, Game Freak,
Creatures Inc. or The Pokémon Company. Pokémon names, characters and images belong to
their respective owners. Data obtained via [PokéAPI](https://pokeapi.co/). No sprite or
artwork files are distributed in this repository.
