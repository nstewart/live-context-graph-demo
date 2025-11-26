.PHONY: help setup up up-agent down logs clean clean-network migrate seed reset-db test lint init-mz init-checkpointer

# Default target
help:
	@echo "FreshMart Digital Twin - Available Commands"
	@echo "============================================"
	@echo ""
	@echo "Setup & Run:"
	@echo "  make setup      - Initial setup (copy .env, build containers)"
	@echo "  make up         - Start all services and initialize Materialize"
	@echo "  make up-agent   - Start all services (including agent) and initialize Materialize"
	@echo "  make down       - Stop all services"
	@echo "  make init-mz    - Initialize Materialize (sources, views, indexes)"
	@echo "  make logs       - Tail logs from all services"
	@echo "  make logs-api   - Tail logs from API service"
	@echo ""
	@echo "Database:"
	@echo "  make migrate         - Run database migrations"
	@echo "  make seed            - Seed demo data"
	@echo "  make reset-db        - Reset database (WARNING: destroys data)"
	@echo "  make init-checkpointer - Initialize agent checkpointer tables"
	@echo ""
	@echo "Development:"
	@echo "  make test       - Run all tests"
	@echo "  make test-api   - Run API tests"
	@echo "  make test-web   - Run Web UI tests"
	@echo "  make lint       - Run linters"
	@echo ""
	@echo "Utilities:"
	@echo "  make clean         - Remove all containers, volumes, and build artifacts"
	@echo "  make clean-network - Remove persistent Docker network (use with caution)"
	@echo "  make shell-db      - Open psql shell to main database"
	@echo "  make shell-mz      - Open psql shell to Materialize emulator"
	@echo "  make shell-api     - Open bash shell in API container"

# Setup
setup:
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "Created .env from .env.example"; \
	fi
	@echo "Building Docker images (this will install all dependencies)..."
	docker-compose build
	@echo ""
	@echo "Setup complete! Run 'make up' or 'make up-agent' to start services."

# Initialize Materialize
init-mz:
	@echo "Initializing Materialize..."
	@echo "Waiting for Materialize to be ready..."
	@sleep 5
	./db/materialize/init.sh
	@echo "Materialize initialized successfully!"

# Initialize Agent Checkpointer
init-checkpointer:
	@echo "Initializing agent checkpointer tables..."
	docker-compose exec agents python -m src.init_checkpointer

# Start services
up:
	@docker network create freshmart-network 2>/dev/null || true
	docker-compose build web zero-permissions
	docker-compose up -d
	@echo ""
	@echo "Services starting..."
	@echo "  - API:        http://localhost:$${API_PORT:-8080}"
	@echo "  - Web UI:     http://localhost:$${WEB_PORT:-5173}"
	@echo "  - PostgreSQL: localhost:$${PG_PORT:-5432}"
	@echo "  - OpenSearch: http://localhost:$${OS_PORT:-9200}"
	@echo ""
	@$(MAKE) init-mz
	@echo ""
	@echo "All services ready! Run 'make logs' to see service output"

up-agent:
	@docker network create freshmart-network 2>/dev/null || true
	docker-compose build web zero-permissions
	docker-compose --profile agent up -d
	@echo ""
	@echo "Waiting for services to be ready..."
	@sleep 3
	@$(MAKE) init-mz
	@echo ""
	@echo "Initializing agent checkpointer..."
	@docker-compose exec agents python -m src.init_checkpointer
	@echo ""
	@echo "All services ready (including agents)!"

down:
	docker-compose --profile agent down

# Logs
logs:
	docker-compose logs -f

logs-api:
	docker-compose logs -f api

logs-sync:
	docker-compose logs -f search-sync

# Database
migrate:
	./db/scripts/run_migrations.sh

seed:
	./db/scripts/seed_demo.sh

reset-db:
	@echo "WARNING: This will destroy all data!"
	@read -p "Are you sure? [y/N] " confirm && [ "$$confirm" = "y" ]
	docker-compose down -v
	docker volume rm freshmart-digital-twin-agent-starter_postgres_data || true
	docker volume rm freshmart-digital-twin-agent-starter_materialize_data || true
	docker-compose up -d db mz
	@echo "Waiting for databases to be ready..."
	@sleep 5
	$(MAKE) migrate
	$(MAKE) seed

# Testing
test: test-api test-web

test-api:
	docker-compose exec api pytest -v

test-web:
	docker-compose exec web npm test

# Linting
lint:
	docker-compose exec api ruff check src/
	docker-compose exec web npm run lint

# Cleanup
clean:
	docker-compose --profile agent down -v --rmi local
	rm -rf api/__pycache__ api/.pytest_cache
	rm -rf search-sync/__pycache__
	rm -rf agents/__pycache__
	rm -rf web/node_modules web/dist
	@echo ""
	@echo "Note: The 'freshmart-network' Docker network was not removed."
	@echo "Run 'make clean-network' if you want to remove it as well."

clean-network:
	@echo "Removing persistent Docker network..."
	docker network rm freshmart-network || true

# Shell access
shell-db:
	docker-compose exec db psql -U $${PG_USER:-postgres} -d $${PG_DATABASE:-freshmart}

shell-mz:
	docker-compose exec mz psql -U $${MZ_USER:-materialize} -d $${MZ_DATABASE:-materialize}

shell-api:
	docker-compose exec api /bin/bash

# Health check
health:
	@echo "Checking service health..."
	@curl -s http://localhost:$${API_PORT:-8080}/health | jq . || echo "API: Not responding"
	@curl -s http://localhost:$${OS_PORT:-9200}/_cluster/health | jq . || echo "OpenSearch: Not responding"
