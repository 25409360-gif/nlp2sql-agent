# NLP2SQL Agent

NLP2SQL Agent is a local Text-to-SQL workbench. It can inspect the current PostgreSQL schema, answer natural-language questions with safe read-only SQL, browse database tables directly, and reserve a separate page for future CSV / XLSX import.

## Features

- Natural-language query page
  - Ask questions in Chinese or English.
  - Generate validated read-only SQL.
  - Execute SQL and show the answer, SQL, result table, schema context, trace, and history.

- Data table browser page
  - List database tables.
  - Open a selected table.
  - View columns and rows in a table grid.
  - Use previous / next pagination.

- File upload import page
  - Placeholder page for the next CSV / XLSX import phase.
  - Upload logic is not implemented yet.

## Requirements

- Docker Desktop with Docker Compose
- Node.js 22 or newer, only for local frontend development
- Python 3.12, only for local backend development

## Environment

Create a local environment file when needed:

```bash
cp .env.example .env
```

The default example configuration uses the mock LLM provider and can run without an external API key.

For an OpenAI-compatible provider such as DeepSeek:

```env
LLM_PROVIDER=openai_compatible
LLM_API_BASE_URL=https://api.deepseek.com
LLM_API_KEY=your_api_key_here
LLM_MODEL=deepseek-chat
```

Do not commit `.env`.

## Start With Docker

From the project root:

```bash
docker compose up -d --build
```

Open the app:

```text
http://localhost:5173
```

Backend API:

```text
http://localhost:8000
```

Adminer database UI:

```text
http://localhost:8080
```

Adminer login:

```text
System: PostgreSQL
Server: postgres
Username: nlp2sql
Password: nlp2sql_password
Database: nlp2sql_demo
```

## Service Ports

| Service | URL or port | Purpose |
| --- | --- | --- |
| Frontend | `http://localhost:5173` | Main web app |
| Backend API | `http://localhost:8000` | FastAPI service |
| Chroma | `http://localhost:8001` | Vector store |
| Adminer | `http://localhost:8080` | Database web UI |
| PostgreSQL | `localhost:5432` | Demo database |
| Redis | `localhost:6379` | Conversation memory |

## Main API Checks

```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/db/health
curl http://localhost:8000/api/cache/health
curl http://localhost:8000/api/schema/metadata
curl http://localhost:8000/api/data/tables
curl "http://localhost:8000/api/data/tables/users/rows?limit=3&offset=0"
```

Chat API:

```bash
curl -s -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"question":"谁迟到次数最多？","session_id":"manual-readme"}'
```

## Example Questions

```text
谁迟到次数最多？
设备使用时长最高的是哪个项目？
哪些项目任务还没完成？
每个项目有多少成员？
最近有哪些项目会议？
把用户表删掉。
```

The last question should be rejected because the agent only supports safe read-only queries.

## Local Development

Start infrastructure:

```bash
docker compose up -d postgres redis chroma
```

Start backend locally:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Start frontend locally in another terminal:

```bash
cd frontend
npm install
VITE_API_BASE_URL=http://localhost:8000 npm run dev -- --host 0.0.0.0
```

## Tests

Backend tests:

```bash
docker compose exec -T backend python -m unittest discover -s tests -p "test_*.py"
```

Frontend build:

```bash
cd frontend
npm run build
```

Docker configuration check:

```bash
docker compose config --quiet
```

## Reset Demo Data

This removes only this project's Docker containers and named volumes, then reloads schema and seed data from `infra/` and `data/`:

```bash
docker compose down -v --remove-orphans
docker compose up -d --build
```

## Troubleshooting

If the frontend cannot connect to the backend:

```bash
docker compose ps
curl http://localhost:8000/health
docker compose logs backend postgres chroma redis
```

If external LLM calls fail, either switch back to the mock provider:

```env
LLM_PROVIDER=mock
LLM_MODEL=mock-llm
```

or confirm that `LLM_PROVIDER`, `LLM_API_BASE_URL`, `LLM_API_KEY`, and `LLM_MODEL` are set correctly in `.env`.

If a port is already in use, stop the other local service or change the matching port mapping in `docker-compose.yml`.
