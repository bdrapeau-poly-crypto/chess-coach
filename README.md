# Chess Coach

Chess Coach ingests public Chess.com games, analyzes a bounded set with Stockfish, builds a
reviewable weakness profile, turns the player's own mistakes into Leitner drills, and exposes
live data to an OpenAI Responses API tool-use coaching loop.

> **Status:** early implementation. Demo games and GM seed profiles are explicitly illustrative;
> they are not
> yet a validated all-grandmaster reference corpus. `local_accuracy` is a transparent score
> derived from average centipawn loss and is not Chess.com Accuracy.

## Architecture

- React 18, Vite, Chart.js, `react-chessboard`, and `react-markdown`
- FastAPI, SQLAlchemy, SQLite locally, and Postgres through `DATABASE_URL`
- Stockfish through `python-chess`, with engine/settings-aware FEN caching
- Database-backed ingest deduplication and per-game failure isolation
- Leitner practice cards generated from the player's own blunder positions
- OpenAI Responses API tools scoped to the requested player, with optional Anthropic fallback

## Local development

Prerequisites: Python 3.11+, Node 20.19+, Stockfish, and an OpenAI Platform API key for the coach.
Codex/ChatGPT subscription usage is separate from API-key billing; a deployed backend needs
an API key from a funded OpenAI Platform project. Never place that key in the frontend.

```bash
brew install stockfish

cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
uvicorn main:app --reload --port 8000
```

In another terminal:

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

Open <http://localhost:5173>. The demo user and illustrative GM profiles are seeded
idempotently on first startup. Its four games are labeled local illustrative fixtures; they are
not represented as a real person's Chess.com history.

## Tests

```bash
cd backend && python -m pytest tests -v && ruff check .  # 129 tests
cd frontend && npm test && npm run lint && npm run typecheck && npm run build  # 24 tests
```

## Deployment

Import the repository into Render as a **Blueprint** so the root `render.yaml` is applied.
The included Blueprint is a disposable free-tier demo: it selects Anthropic, requires
`ANTHROPIC_API_KEY` and `CORS_ORIGINS`, and explicitly permits temporary SQLite storage. Data
can reset whenever the free service sleeps, restarts, or redeploys, and the nightly refresh is
disabled. The coach defaults to Claude Haiku 4.5 for the lowest current Claude API token cost
that supports this short tool-use workflow. For durable production use, configure external Postgres through `DATABASE_URL`,
disable `ALLOW_EPHEMERAL_DATABASE`, and add a scheduled refresh service. OpenAI remains
supported as an optional coach provider.

Import `frontend/` into Vercel and set `VITE_API_URL` to the Render API URL. Vercel creates
preview deployments for pull requests when Git integration is enabled.

## API

- `POST /ingest/{username}` and `GET /ingest/jobs/{job_id}`
- `GET /profile/{username}`
- `GET /style/{username}/match` and `GET /style-gap/{username}`
- `GET /blunders/{username}` and `GET /openings/{username}`
- `GET|POST /drill/{username}/queue`, `POST /drill/{username}/attempt`, and
  `GET /drill/{username}/mastery`
- `POST /coach`
- `GET /health` and `GET /health/stockfish`

## Data and security boundaries

Chess.com PubAPI data is public and read-only, but drill history and coach conversations are
application data. Do not expose write endpoints publicly without adding authentication and
per-user authorization. Secrets remain server-side and must never use a `VITE_` prefix.
