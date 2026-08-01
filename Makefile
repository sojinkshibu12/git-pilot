.PHONY: dev-backend dev-frontend test lint fmt migrate db-up docs compose-up compose-down

db-up:
	docker compose up -d postgres redis

dev-backend:
	cd backend && uvicorn app.main:app --reload --port 8000

dev-frontend:
	cd frontend && npm run dev

migrate:
	cd backend && alembic upgrade head

test:
	cd backend && pytest

lint:
	cd backend && ruff check app tests && mypy app
	cd frontend && npm run lint

fmt:
	cd backend && ruff format app tests
	cd frontend && npx prettier --write .

compose-up:
	docker compose --profile full up --build -d

compose-down:
	docker compose down
