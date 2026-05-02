.PHONY: up down logs rebuild seed migrate types-py types-ts observer help

help:
	@echo "Mycelium dev commands:"
	@echo "  make up         - bring up the full stack (excluding observer)"
	@echo "  make down       - tear down + remove volumes"
	@echo "  make logs       - tail logs"
	@echo "  make rebuild    - rebuild + restart"
	@echo "  make seed       - re-run the seed script"
	@echo "  make migrate    - run alembic upgrade head"
	@echo "  make observer   - run the local observer (NOT in docker)"

up:
	docker compose up --build

down:
	docker compose down -v

logs:
	docker compose logs -f --tail=200

rebuild:
	docker compose up --build --force-recreate

seed:
	docker compose run --rm seed

migrate:
	docker compose run --rm api bash -lc "cd /workspace/packages/db/python && alembic upgrade head"

# Observer runs LOCALLY. NOT in docker.
observer:
	cd services/observer && poetry install && poetry run python main.py

types-ts:
	pnpm --filter @mycelium/shared-types build

types-py:
	@echo "shared-types is a path-installed dependency; nothing to build."
