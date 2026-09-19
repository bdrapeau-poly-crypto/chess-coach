# Chess Coach

Chess Coach ingests public Chess.com games, analyzes a bounded set with Stockfish, builds a
reviewable weakness profile, turns the player's own mistakes into Leitner drills, and exposes
live data to an Anthropic or OpenAI tool-use coaching loop.

> **Status:** early implementation. Demo games and GM seed profiles are explicitly illustrative;
> they are not
> yet a validated all-grandmaster reference corpus. `local_accuracy` is a transparent score
> derived from average centipawn loss and is not Chess.com Accuracy.

## Architecture

- React 18, Vite, Chart.js, `react-chessboard`, and `react-markdown`
- FastAPI, SQLAlchemy, SQLite locally, Postgres through `DATABASE_URL`, and Alembic migrations
- Stockfish through `python-chess`, with engine/settings-aware FEN caching
- Database-backed ingest deduplication and per-game failure isolation
- Leitner practice cards generated from the player's own blunder positions
- Claude or OpenAI tools scoped to the requested player
- Signed private-beta sessions, database-backed request limits, and usage instrumentation

## Local development

Prerequisites: Python 3.11+, Node 20.19+, Stockfish, and an Anthropic or OpenAI API key for the
coach. Codex/ChatGPT subscriptions are separate from API billing. Never place an AI provider
key, `APP_ACCESS_KEY`, or `SESSION_SECRET` in the frontend.

```bash
brew install stockfish

cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
alembic upgrade head
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
not represented as a real person's Chess.com history. Set `AUTH_REQUIRED=true`, a private
`APP_ACCESS_KEY` of at least 16 characters, and a random `SESSION_SECRET` of at least 32
characters to exercise private-beta authentication locally.

## Tests

```bash
cd backend && python -m pytest tests -v && ruff check .
cd frontend && npm test && npm run lint && npm run typecheck && npm run build
```

## Deployment

Import the repository into Render as a **Blueprint** so the root `render.yaml` is applied. Before
deploying, configure these secret environment variables on the web service:

- `DATABASE_URL`: a durable PostgreSQL connection URL
- `ANTHROPIC_API_KEY`: the server-side coach credential
- `APP_ACCESS_KEY`: the private-beta passphrase entered by authorized users
- `SESSION_SECRET`: a random signing secret of at least 32 characters
- `CORS_ORIGINS`: the exact Vercel production origin

The container runs `alembic upgrade head` before starting the API. `ALLOW_EPHEMERAL_DATABASE`
is false in production, so a missing PostgreSQL URL fails safely instead of silently returning
to disposable SQLite. The coach defaults to Claude Haiku 4.5; OpenAI remains supported. Render
deploys only after GitHub checks pass. To avoid two deployments when `render.yaml` changes, keep
Blueprint Auto Sync off and manually sync infrastructure changes after reviewing them.

Import `frontend/` into Vercel and set `VITE_API_URL` to the Render API URL. Vercel creates
preview deployments for pull requests when Git integration is enabled.

### Nightly refresh

The production refresh runs from `.github/workflows/nightly-refresh.yml` at 07:17 UTC, rather
than from the sleeping free Render web process. Configure the GitHub Actions secret
`CHESS_COACH_ACCESS_KEY` with the same value as Render's `APP_ACCESS_KEY`. The workflow wakes the
API, exchanges the access key for a short-lived session, loads the exact non-demo Chess.com
usernames previously submitted for ingestion, queues each refresh, and polls it to a terminal
status. It processes at most five users per run and fails visibly on job failure or timeout.
`workflow_dispatch` accepts an optional username list for a bounded manual override.
Ingest workers renew a ten-minute lease after every analyzed game and continuously requeue expired
work, allowing an interrupted Render deployment to resume without waiting for a long fixed lease.

### Production monitoring and restore drills

`.github/workflows/production-monitor.yml` checks the frontend, API, Stockfish probe, deployed
Git commit, authentication, and one-day telemetry every hour. Three ingest failures in one day
fail the monitor by default. A failed monitor opens a deduplicated GitHub issue. Set
`COACH_DAILY_TOKEN_ALERT` to a nonzero repository-variable threshold to add a coarse token-volume
guard; use Anthropic Console's workspace spend notification for an authoritative dollar alert.

The coach also enforces a durable, fail-closed API cost ledger before each Anthropic call. The
default `AI_DAILY_BUDGET_USD=0.50` is the 30-day equivalent of a $15 monthly budget. Each call
reserves a conservative maximum, reconciles that reservation to actual token cost, and retains
unknown-cost reservations when the provider outcome cannot be accounted for. The hourly
production monitor opens an alert if the daily coach budget is exhausted.

`.github/workflows/neon-restore-drill.yml` runs weekly. It creates a short-lived point-in-time
restore branch from `production` at five minutes before the run, validates the expected schema,
Alembic head, and restored user data, then deletes the drill branch. The branch also expires after
two hours if cleanup is interrupted. The workflow uses a project-scoped
`NEON_PROJECT_API_KEY`; it does not reuse the account-wide MCP credential.

## API

- `POST /ingest/{username}` and `GET /ingest/jobs/{job_id}`
- `GET /profile/{username}`
- `GET /style/{username}/match` and `GET /style-gap/{username}`
- `GET /blunders/{username}` and `GET /openings/{username}`
- `GET|POST /drill/{username}/queue`, `POST /drill/{username}/attempt`, and
  `GET /drill/{username}/mastery`
- `POST /coach`
- `GET|POST /auth/session` and authenticated `GET /metrics/summary`
- `GET /health` and `GET /health/stockfish`

## Data and security boundaries

Chess.com PubAPI data is public and read-only, but drill history, operational metrics, and coach
activity are application data. In private-beta mode, ingestion, coaching, real-player drill
mutations, job status, and metrics require a short-lived signed bearer token. The long-lived
access key is exchanged once and is not retained by the frontend. The shared demo drill is
deliberately stateless. This is access control for a private beta, not individual Chess.com
account ownership verification; use an identity provider before supporting unrelated users.
Secrets remain server-side and must never use a `VITE_` prefix.

Usage instrumentation stores request duration, provider/model, token counts, prompt-cache
read/write counts, tool rounds, ingest totals, and Stockfish cache hit/miss counts. It does not
store coach prompts or responses. View aggregates through authenticated `GET /metrics/summary`.
