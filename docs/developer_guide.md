# Developer Guide
RUN:
alembic :
    uv run alembic init migrations
    uv run alembic revision --autogenerate -m "create auth metadata tables"
    uv run alembic upgrade head
Seed users data:
    uv run python scripts/seed_auth.py
FastAPI:
    uv run uvicorn graphdba.app.app:app --reload --port 8000
git commit:
    git add .
    git commit -m "message"
    git push
frontend run:
    cd frontend
    npm install
    npm run dev
docker run:
    docker compose up -d
    docker compose down
alert mock request:
    curl -X POST http://127.0.0.1:8000/api/v1/alerts -H "Content-Type: application/json" -d @/Users/hunkyhsu/CursorProjects/demo/template.txt