.PHONY: install dev api web test build docker mock-llm

install:
	cd backend && python3 -m pip install -r requirements.txt pytest
	cd frontend && npm install

api:
	cd backend && uvicorn app.main:app --reload --reload-dir app --port 8000

web:
	cd frontend && npm run dev

dev:
	@echo "API on :8000, UI on :5173 (Ctrl+C stops both)"
	@trap 'kill 0' INT; (cd backend && uvicorn app.main:app --reload --reload-dir app --port 8000) & (cd frontend && npm run dev) & wait

test:
	cd backend && python3 -m pytest -q

build:
	cd frontend && npm run build && rm -rf ../backend/static && cp -r dist ../backend/static

docker:
	docker compose up --build

mock-llm:
	cd backend && uvicorn tests.mock_llm:app --port 11999
