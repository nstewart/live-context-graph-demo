.PHONY: help setup label labels label-check label-leaks label-lint label-ci up up-agent up-agent-bundling down logs clean clean-network migrate seed reset-db test lint init-mz init-checkpointer setup-load-gen load-gen load-gen-demo load-gen-standard load-gen-peak load-gen-stress load-gen-demand load-gen-supply load-gen-health test-load-gen up-aws up-agent-aws up-agent-bundling-aws down-aws aws-tunnel aws-ssh aws-logs aws-status aws-debug

# Detect docker compose command (prefer "docker compose" over "$(DOCKER_COMPOSE)")
DOCKER_COMPOSE := $(shell if docker compose version >/dev/null 2>&1; then echo "docker compose"; else echo "$(DOCKER_COMPOSE)"; fi)

# Ownership tags required on new AWS resources by the RequireTagsScratch SCP
# (MaterializeInc/i2#3620). Override on the command line, e.g.
#   make up-agent-aws TEAM="Cloud" DELETE_AFTER_HOURS=72
OWNER_EMAIL ?= $(shell git config user.email)
REASON ?= Freshmart Demo
TEAM ?= Field Engineering
DELETE_AFTER_HOURS ?= 24
AWS_TAG_ENV = OWNER_EMAIL="$(OWNER_EMAIL)" REASON="$(REASON)" TEAM="$(TEAM)" \
	DELETE_AFTER_HOURS="$(DELETE_AFTER_HOURS)" DELETE_AFTER="$(DELETE_AFTER)"

# White-label skin, e.g. `make up LABEL=life-insurance`. Optional; the demo
# defaults to freshmart. See labels/ and docs/WHITE_LABELING.md.
LABEL ?= freshmart
LABEL_ENV = DEMO_LABEL="$(LABEL)"

# The resolver needs PyYAML to parse labels and jsonschema to validate them against
# labels/schema.json. Use the system interpreter only when it has BOTH -- otherwise
# validation would silently skip -- and fall back to uv (a documented prerequisite).
LABEL_PY := $(shell if python3 -c 'import yaml, jsonschema' >/dev/null 2>&1; then \
		echo "python3"; \
	else \
		echo "uv run --no-project --quiet --with pyyaml --with jsonschema python3"; \
	fi)

# Default target
help:
	@echo "FreshMart Digital Twin - Available Commands"
	@echo "============================================"
	@echo ""
	@echo "White-labeling:"
	@echo "  make labels            - List available demo labels"
	@echo "  make label             - Resolve + validate a label without starting anything"
	@echo "  make label-ci          - All white-label CI guards (drift, leaks, lint)"
	@echo "  Add LABEL=<name> to any up/seed/reset-db target, e.g."
	@echo "    make up LABEL=life-insurance"
	@echo "  Current: LABEL=$(LABEL)"
	@echo ""
	@echo "Setup & Run:"
	@echo "  make setup             - Initial setup (copy .env, build containers)"
	@echo "  make up                - Start all services (Materialize auto-initializes)"
	@echo "  make up-agent          - Start all services including agent (Materialize auto-initializes)"
	@echo "  make up-agent-bundling - Start with delivery bundling enabled (CPU intensive)"
	@echo "  make down              - Stop all services"
	@echo "  make init-mz    - Manually re-initialize Materialize (usually not needed)"
	@echo "  make logs       - Tail logs from all services"
	@echo "  make logs-api   - Tail logs from API service"
	@echo "  make logs-sync  - Tail logs from the embedding pipeline (connect + tap)"
	@echo ""
	@echo "Database:"
	@echo "  make migrate         - Run database migrations"
	@echo "  make seed            - Seed demo data"
	@echo "  make reset-db        - Reset database (WARNING: destroys data)"
	@echo "  make init-checkpointer - Initialize agent checkpointer tables"
	@echo ""
	@echo "Load Generation:"
	@echo "  make setup-load-gen    - Install uv and set up load generator (auto-runs before other targets)"
	@echo "  make load-gen          - Start load generator (demo profile)"
	@echo "  make load-gen-demo     - Start with demo profile (5 orders/min)"
	@echo "  make load-gen-standard - Start with standard profile (20 orders/min)"
	@echo "  make load-gen-peak     - Start with peak profile (60 orders/min)"
	@echo "  make load-gen-stress   - Start with stress profile (200 orders/min)"
	@echo "  make load-gen-demand   - Start demand-only generator (orders, customers)"
	@echo "  make load-gen-supply   - Start supply-only generator (courier dispatch)"
	@echo "  make load-gen-health   - Check API health for load generator"
	@echo "  make test-load-gen     - Run load generator tests"
	@echo ""
	@echo "AWS Deployment:"
	@echo "  make up-aws                - Deploy to EC2 (without agent)"
	@echo "  make up-agent-aws          - Deploy to EC2 (with agent)"
	@echo "  make up-agent-bundling-aws - Deploy to EC2 (with agent + bundling)"
	@echo "  make down-aws              - Tear down EC2 instance and resources"
	@echo "  make aws-tunnel            - Re-establish SSH tunnel"
	@echo "  make aws-ssh               - SSH into the EC2 instance"
	@echo "  make aws-logs              - Tail remote Docker Compose logs"
	@echo "  make aws-debug             - Preflight check (AWS CLI, IAM, region, tools)"
	@echo "  make aws-status            - Check tunnel and instance status"
	@echo ""
	@echo "  Required resource tags (overridable):"
	@echo "    OWNER_EMAIL=$(OWNER_EMAIL)"
	@echo "    TEAM=$(TEAM)"
	@echo "    REASON=$(REASON)"
	@echo "    DELETE_AFTER_HOURS=$(DELETE_AFTER_HOURS)"
	@echo "    e.g. make up-agent-aws TEAM=\"Cloud\" DELETE_AFTER_HOURS=72"
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
	docker compose build
	@echo ""
	@echo "Setup complete! Run 'make up' or 'make up-agent' to start services."

# White-labeling
#
# `label` resolves labels/$(LABEL).yaml into the artifacts every service reads
# and validates it. Every up* target depends on it, so an unknown or malformed
# label fails before Docker is touched.
label:
	@$(LABEL_PY) tools/resolve_label.py --label "$(LABEL)"

labels:
	@$(LABEL_PY) tools/resolve_label.py --list

# CI guards for white-labeling. `label-check` catches a stale committed web
# artifact, `label-leaks` catches a label that inherited the default vertical's
# wording, and `label-lint` catches the brand being hardcoded back into source.
label-check:
	@$(LABEL_PY) tools/resolve_label.py --check

label-leaks:
	@$(LABEL_PY) tools/check_label_leaks.py

label-lint:
	@bash tools/label_lint.sh

label-ci: label-check label-leaks label-lint

# Initialize Materialize
init-mz:
	@echo "Initializing Materialize..."
	$(DOCKER_COMPOSE) run --rm -T materialize-init
	@echo "Materialize initialized successfully!"

# Initialize Agent Checkpointer
init-checkpointer:
	@echo "Initializing agent checkpointer tables..."
	$(DOCKER_COMPOSE) exec agents env PYTHONPATH=/app python -m src.init_checkpointer

# Start services
up: label
	@docker network create freshmart-network 2>/dev/null || true
	$(LABEL_ENV) $(DOCKER_COMPOSE) build web zero-permissions api
	@# Force recreate materialize-init to ensure views are updated based on ENABLE_DELIVERY_BUNDLING
	$(DOCKER_COMPOSE) rm -f materialize-init 2>/dev/null || true
	$(LABEL_ENV) $(DOCKER_COMPOSE) up -d --remove-orphans
	@echo ""
	@echo "Waiting for databases to be ready..."
	@sleep 5
	@echo "Running migrations..."
	@$(MAKE) migrate
	@echo "Loading seed data..."
	@$(MAKE) seed LABEL="$(LABEL)"
	@echo ""
	@echo "Services starting...  (label: $(LABEL))"
	@echo "  - API:        http://localhost:$${API_PORT:-8080}"
	@echo "  - Web UI:     http://localhost:$${WEB_PORT:-5173}"
	@echo "  - PostgreSQL: localhost:$${PG_PORT:-5432}"
	@echo "  - OpenSearch: http://localhost:$${OS_PORT:-9200}"
	@echo ""
	@echo "Note: Materialize is automatically initialized via materialize-init service"
	@echo "      OpenSearch is populated automatically once the kafka-connect sink starts"
	@echo ""
	@echo "All services ready! Run 'make logs' to see service output"

up-agent: label
	@docker network create freshmart-network 2>/dev/null || true
	$(LABEL_ENV) $(DOCKER_COMPOSE) build web zero-permissions api
	@# Force recreate materialize-init to ensure views are updated based on ENABLE_DELIVERY_BUNDLING
	$(DOCKER_COMPOSE) rm -f materialize-init 2>/dev/null || true
	$(LABEL_ENV) $(DOCKER_COMPOSE) --profile agent up -d
	@echo ""
	@echo "Waiting for databases to be ready..."
	@sleep 5
	@echo "Running migrations..."
	@$(MAKE) migrate
	@echo ""
	@echo "Note: Materialize views are initialized automatically by the materialize-init container."
	@echo "      Run 'make init-mz' manually only if you need to re-initialize views."
	@sleep 3
	@echo "Loading seed data..."
	@$(MAKE) seed LABEL="$(LABEL)"
	@echo ""
	@echo "Waiting for agent services to be ready..."
	@sleep 3
	@echo ""
	@echo "Ensuring agents container is on freshmart-network..."
	@docker network connect freshmart-network $$($(DOCKER_COMPOSE) ps -q agents) 2>/dev/null || true
	@echo "Initializing agent checkpointer..."
	@$(DOCKER_COMPOSE) exec agents env PYTHONPATH=/app python -m src.init_checkpointer
	@echo ""
	@echo "Note: Materialize is automatically initialized via materialize-init service"
	@echo "      OpenSearch is populated automatically once the kafka-connect sink starts"
	@echo ""
	@echo "All services ready (including agents)!"

up-agent-bundling: label
	@docker network create freshmart-network 2>/dev/null || true
	ENABLE_DELIVERY_BUNDLING=true $(LABEL_ENV) $(DOCKER_COMPOSE) build web zero-permissions api
	@# Force recreate materialize-init to ensure bundling views are created
	$(DOCKER_COMPOSE) rm -f materialize-init 2>/dev/null || true
	ENABLE_DELIVERY_BUNDLING=true $(LABEL_ENV) $(DOCKER_COMPOSE) --profile agent up -d
	@echo ""
	@echo "Waiting for databases to be ready..."
	@sleep 5
	@echo "Running migrations..."
	@$(MAKE) migrate
	@echo ""
	@echo "Note: Materialize views are initialized automatically by the materialize-init container."
	@echo "      Delivery bundling is ENABLED (CPU intensive recursive views)."
	@sleep 3
	@echo "Loading seed data..."
	@$(MAKE) seed LABEL="$(LABEL)"
	@echo ""
	@echo "Waiting for agent services to be ready..."
	@sleep 3
	@echo ""
	@echo "Ensuring agents container is on freshmart-network..."
	@docker network connect freshmart-network $$($(DOCKER_COMPOSE) ps -q agents) 2>/dev/null || true
	@echo "Initializing agent checkpointer..."
	@$(DOCKER_COMPOSE) exec agents env PYTHONPATH=/app python -m src.init_checkpointer
	@echo ""
	@echo "Note: Materialize is automatically initialized via materialize-init service"
	@echo "      Delivery bundling is ENABLED - expect higher CPU usage (~460s compute time)"
	@echo "      OpenSearch is populated automatically once the kafka-connect sink starts"
	@echo ""
	@echo "All services ready (including agents with delivery bundling)!"

down:
	$(DOCKER_COMPOSE) --profile agent down -v --remove-orphans
	@# Belt-and-suspenders: explicitly drop named volumes that have lived
	@# under different project names over time. The `-v` above takes care
	@# of the current ones; these handle stale leftovers from renames.
	@docker volume rm live-context-graph-demo_postgres_data 2>/dev/null || true
	@docker volume rm live-context-graph-demo_zero_data 2>/dev/null || true
	@docker volume rm live-context-graph-demo_opensearch_data 2>/dev/null || true
	@docker volume rm live-agent-ontology-demo_postgres_data 2>/dev/null || true

# Logs
logs:
	$(DOCKER_COMPOSE) logs -f

logs-api:
	$(DOCKER_COMPOSE) logs -f api

logs-sync:
	$(DOCKER_COMPOSE) logs -f connect connect-bootstrap propagation-tap embeddings

# Database
migrate:
	./db/scripts/run_migrations.sh

seed: label
	@echo "Building and running database seeder (label: $(LABEL))..."
	$(DOCKER_COMPOSE) --profile seed build db-seed
	$(LABEL_ENV) $(DOCKER_COMPOSE) --profile seed run --rm db-seed

reset-db: label
	@echo "WARNING: This will destroy all data!"
	@read -p "Are you sure? [y/N] " confirm && [ "$$confirm" = "y" ]
	$(DOCKER_COMPOSE) down -v
	docker volume rm freshmart-digital-twin-agent-starter_postgres_data || true
	docker volume rm freshmart-digital-twin-agent-starter_materialize_data || true
	$(LABEL_ENV) $(DOCKER_COMPOSE) up -d db mz
	@echo "Waiting for databases to be ready..."
	@sleep 5
	$(MAKE) migrate
	$(MAKE) seed LABEL="$(LABEL)"

# Testing
test: label-ci test-api test-web test-propagation

test-api:
	$(DOCKER_COMPOSE) exec api pytest -v

test-web:
	$(DOCKER_COMPOSE) exec web npm test

# Runs on the host (pure-Python, no stack/confluent_kafka needed).
# Install deps once with: pip install -r propagation-tap/requirements-dev.txt
test-propagation:
	cd propagation-tap && python3 -m pytest tests/ -v

# Linting
lint:
	$(DOCKER_COMPOSE) exec api ruff check src/
	$(DOCKER_COMPOSE) exec web npm run lint

# Cleanup
clean:
	$(DOCKER_COMPOSE) --profile agent down -v --rmi local
	rm -rf api/__pycache__ api/.pytest_cache
	rm -rf propagation-tap/__pycache__ propagation-tap/src/__pycache__
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
	$(DOCKER_COMPOSE) exec db psql -U $${PG_USER:-postgres} -d $${PG_DATABASE:-freshmart}

shell-mz:
	$(DOCKER_COMPOSE) exec mz psql -U $${MZ_USER:-materialize} -d $${MZ_DATABASE:-materialize}

shell-api:
	$(DOCKER_COMPOSE) exec api /bin/bash

# Health check
health:
	@echo "Checking service health..."
	@curl -s http://localhost:$${API_PORT:-8080}/health | jq . || echo "API: Not responding"
	@curl -s http://localhost:$${OS_PORT:-9200}/_cluster/health | jq . || echo "OpenSearch: Not responding"

# Load Generation
# Check for uv installation and set up environment
setup-load-gen:
	@if ! command -v uv &> /dev/null; then \
		echo "Error: 'uv' is not installed."; \
		echo ""; \
		echo "To install uv:"; \
		echo "  macOS/Linux: curl -LsSf https://astral.sh/uv/install.sh | sh"; \
		echo "  macOS (Homebrew): brew install uv"; \
		echo "  Windows: powershell -c \"irm https://astral.sh/uv/install.ps1 | iex\""; \
		echo ""; \
		echo "For more info: https://github.com/astral-sh/uv"; \
		exit 1; \
	fi
	@echo "Setting up load generator (uv will install Python if needed)..."
	@cd load-generator && uv venv --quiet || true
	@cd load-generator && uv pip install --quiet -r requirements.txt

load-gen: setup-load-gen load-gen-demo

load-gen-demo: setup-load-gen
	@echo "Starting load generator with demo profile..."
	@cd load-generator && uv run --no-sync python -m loadgen start --profile demo

load-gen-standard: setup-load-gen
	@echo "Starting load generator with standard profile..."
	@cd load-generator && uv run --no-sync python -m loadgen start --profile standard

load-gen-peak: setup-load-gen
	@echo "Starting load generator with peak profile..."
	@cd load-generator && uv run --no-sync python -m loadgen start --profile peak

load-gen-stress: setup-load-gen
	@echo "Starting load generator with stress profile..."
	@cd load-generator && uv run --no-sync python -m loadgen start --profile stress

load-gen-demand: setup-load-gen
	@echo "Starting demand-only load generator (orders, customers, inventory)..."
	@cd load-generator && uv run --no-sync python -m loadgen start --profile demo --demand-only

load-gen-supply: setup-load-gen
	@echo "Starting supply-only load generator (courier dispatch)..."
	@cd load-generator && uv run --no-sync python -m loadgen start --profile demo --supply-only

load-gen-health: setup-load-gen
	@cd load-generator && uv run --no-sync python -m loadgen health

test-load-gen: setup-load-gen
	@echo "Running load generator tests..."
	@cd load-generator && uv run --no-sync pytest -v

# AWS Deployment
aws-debug:
	@$(AWS_TAG_ENV) bash aws/debug.sh

up-aws: label
	@$(AWS_TAG_ENV) $(LABEL_ENV) bash aws/deploy.sh "docker compose up -d --remove-orphans"

up-agent-aws: label
	@$(AWS_TAG_ENV) $(LABEL_ENV) bash aws/deploy.sh "docker compose --profile agent up -d --remove-orphans"

up-agent-bundling-aws: label
	@$(AWS_TAG_ENV) $(LABEL_ENV) ENABLE_DELIVERY_BUNDLING=true bash aws/deploy.sh "ENABLE_DELIVERY_BUNDLING=true docker compose --profile agent up -d --remove-orphans"

down-aws:
	@bash aws/teardown.sh

aws-tunnel:
	@bash aws/ssh-tunnel.sh stop 2>/dev/null || true
	@bash aws/ssh-tunnel.sh start

aws-ssh:
	@if [ ! -f aws/.state/public-ip ] || [ ! -f aws/.state/key-file ]; then \
		echo "Error: No instance state found. Run 'make up-aws' first."; \
		exit 1; \
	fi
	ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR \
		-i "$$(cat aws/.state/key-file)" \
		ec2-user@"$$(cat aws/.state/public-ip)"

aws-logs:
	@if [ ! -f aws/.state/public-ip ] || [ ! -f aws/.state/key-file ]; then \
		echo "Error: No instance state found. Run 'make up-aws' first."; \
		exit 1; \
	fi
	ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR \
		-i "$$(cat aws/.state/key-file)" \
		ec2-user@"$$(cat aws/.state/public-ip)" \
		"cd ~/app && docker compose --profile agent logs -f"

aws-status:
	@echo "=== Instance Status ==="
	@if [ -f aws/.state/instance-id ]; then \
		INSTANCE_ID=$$(cat aws/.state/instance-id); \
		echo "Instance ID: $$INSTANCE_ID"; \
		aws ec2 describe-instances --instance-ids "$$INSTANCE_ID" \
			--query "Reservations[0].Instances[0].{State:State.Name,IP:PublicIpAddress,Type:InstanceType}" \
			--output table 2>/dev/null || echo "  Instance not found"; \
	else \
		echo "  No instance state found"; \
	fi
	@echo ""
	@echo "=== SSH Tunnel Status ==="
	@bash aws/ssh-tunnel.sh status 2>/dev/null || true
