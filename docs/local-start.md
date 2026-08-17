## 1. Deja únicamente PostgreSQL en Docker

Abre PowerShell:

```powershell
Set-Location C:\Users\jeron\Desktop\Pokedex-RAG

docker compose stop api
docker compose up -d db
docker compose ps
```

`pokedex-db` debe aparecer como `healthy`.

## 2. Arranca la API local

En otra ventana de PowerShell:

```powershell
Set-Location C:\Users\jeron\Desktop\Pokedex-RAG\apps\api

$env:CORS_ALLOWED_ORIGINS = 'http://localhost:3000,http://127.0.0.1:3000'

poetry install
poetry run uvicorn api.main:app --factory --host 127.0.0.1 --port 8000 --reload
```

Déjala abierta. Debes ver:

```text
Uvicorn running on http://127.0.0.1:8000
```

No vuelvas a ejecutar `cd apps/api`: ya estás dentro.

## 3. Configura el frontend

En esa misma tercera ventana:

```powershell
Set-Location C:\Users\jeron\Desktop\Pokedex-RAG\apps\web

Copy-Item .env.example .env.local -Force
Get-Content .env.local
```

Comprueba que contiene exactamente:

```dotenv
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
NEXT_PUBLIC_POKEDEX_MAX_ID=151
NEXT_PUBLIC_API_KEY=
```

## 4. Arranca el frontend

```powershell
pnpm install
pnpm dev
```

Déjalo abierto y entra en:

[http://localhost:3000](http://localhost:3000)

Haz una recarga forzada con `Ctrl+Shift+R`.