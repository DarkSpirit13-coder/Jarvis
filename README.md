<!-- Production readiness guide for the JARVIS monorepo. -->
# JARVIS

JARVIS is a production-oriented AI Operating System monorepo with a FastAPI backend, Next.js 15 frontend, PostgreSQL, Redis, Docker Compose, Alembic, SQLAlchemy 2.0, Pydantic v2, Pytest, ESLint, Prettier, and GitHub Actions CI.

## Structure

- `backend/`: async FastAPI service with clean API, service, agent, memory, tool, voice, database, and websocket boundaries.
- `frontend/`: typed Next.js 15 application using Tailwind CSS.
- `desktop/electron/`: Electron shell entrypoint for a desktop wrapper.
- `docker/`: infrastructure bootstrap files.
- `docs/`: architectural documentation.
- `scripts/`: operational helper scripts.

## Local Start

1. Copy `.env.example` to `.env` and replace `JWT_SECRET_KEY`.
2. Run `docker compose up --build`.
3. Open `http://localhost:3000`.
4. Check the backend at `http://localhost:8000/api/health`.

## Backend Development

```bash
cd backend
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
pytest
ruff check .
```

## Frontend Development

```bash
cd frontend
npm install
npm run dev
npm run lint
npm run format:check
```

## Production Notes

Sprint 2 adds the first working intelligence layer:

- OpenAI-compatible LLM provider with streaming, JSON mode, tool calling metadata, temperature, model, and max-token controls.
- LLM-backed planner that returns structured goals, reasoning, steps, tool calls, and memory requirements.
- Dynamic tool registry with Browser, File, Terminal, Time, System Info, and Echo tools.
- Tool router with sequential execution, parallel groups, timeouts, retries, structured errors, and latency logging.
- In-process memory engine with `save`, `search`, `retrieve`, and `summarize` interfaces for future vector database implementations.
- Conversation manager that loads memory, plans, executes tools, generates final answers, streams tokens, and stores conversation traces.
- Streaming chat UI with Markdown rendering, thinking state, conversation history, and auto-scroll.

External AI calls require `OPENAI_API_KEY`. Memory and tools are production-shaped interfaces, and the local memory implementation is process-local until a durable database or vector store is configured.

## Environment Variables

- `OPENAI_API_KEY`: API key for an OpenAI-compatible provider.
- `OPENAI_MODEL`: Chat model name, default `gpt-5.5`.
- `OPENAI_BASE_URL`: Compatible API base URL, default `https://api.openai.com/v1`.
- `LLM_TEMPERATURE`: Sampling temperature.
- `LLM_MAX_TOKENS`: Maximum generated tokens.
- `TOOL_TIMEOUT_SECONDS`: Per-tool timeout.
- `TOOL_RETRIES`: Retry attempts for failed tools.
- `WORKSPACE_ROOT`: Root directory available to file and terminal tools.

## API Examples

```bash
curl http://localhost:8000/api/health
```

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"What time is it?","conversation_id":"local","user_id":"operator"}'
```

```bash
curl http://localhost:8000/api/tools
```

`POST /api/chat/stream` returns server-sent events with token payloads. WebSocket streaming is available at `/ws/conversations/{conversation_id}` using JSON messages shaped as `{"message":"hello","user_id":"operator"}` and cancellation messages shaped as `{"type":"cancel"}`.

## Future Work

- Durable PostgreSQL-backed conversation repository.
- Vector memory provider and memory summarization with an LLM budget policy.
- Provider-specific adapters beyond OpenAI-compatible chat completions.
- Tool permission policies for production deployments.
- Authenticated WebSocket sessions and per-user memory isolation backed by persisted identities.
