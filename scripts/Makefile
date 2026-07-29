# Makefile - Essential commands

include .env
export

.PHONY: benchmark
benchmark:
	@bash -c "source venv/bin/activate && python scripts/benchmark/__main__.py"

.PHONY: help
help:
	@echo "Available commands:"
	@echo "  setup       - Create venv, install deps, compile protos"
	@echo "  proto       - Compile protobuf files"
	@echo "  up          - Build and start all dev services"
	@echo "  down        - Stop all dev services"
	@echo "  test        - Run all tests"
	@echo "  test-auth   - Run auth service tests"
	@echo "  test-gateway - Run gateway service tests"
	@echo "  test-ingestion - Run ingestion service tests"
	@echo "  test-analytics - Run analytics workers tests"
	@echo "  test-query  - Run query service tests"
	@echo "  test-migrations - Run migration service tests"
	@echo "  benchmark   - Measure max sustainable ingestion logs/s (auto-ramp, gzip, fresh key, DB verify)"
	@echo ""
	@echo "Database Commands (migration service, ARGS=... is passed through):"
	@echo "  db-status   - Show schema version, current revision and pending revisions"
	@echo "  db-upgrade  - Apply pending migrations"
	@echo "  db-downgrade - Roll back migrations (ARGS=\"--database auth --version 1\")"
	@echo "  db-migrate  - Create a revision file (ARGS=\"--database auth -m message\")"
	@echo "  db-history  - Show revision history"
	@echo "  db-stamp    - Mark a revision as applied"
	@echo ""
	@echo "Production Commands:"
	@echo "  prod-deploy - Build and push production images to registry"
	@echo "  prod-up     - Start production services"
	@echo "  prod-down   - Stop production services"

# ==================== Setup ====================

.PHONY: setup
setup:
	@if [ ! -f .env ]; then cp .env.example .env; echo "Created .env"; fi
	@if [ ! -d "venv" ]; then python3 -m venv venv; fi
	@bash -c "source venv/bin/activate && \
		cd services/auth && pip install -r requirements.txt && \
		cd ../gateway && pip install -r requirements.txt && \
		cd ../ingestion && pip install -r requirements.txt && \
		cd ../analytics && pip install -r requirements.txt && \
		cd ../query && pip install -r requirements.txt && \
		cd ../migrations && pip install -r requirements.txt"
	make proto
	@echo "Setup complete. Edit .env if needed, then run 'make up'"

# ==================== Protobuf ====================

.PHONY: proto
proto:
	@echo "Compiling protobuf files..."
	@mkdir -p services/auth/auth_service/proto
	@mkdir -p services/gateway/gateway_service/proto
	@mkdir -p services/ingestion/ingestion_service/proto
	@mkdir -p services/query/query_service/proto
	@touch services/auth/auth_service/proto/__init__.py
	@touch services/gateway/gateway_service/proto/__init__.py
	@touch services/ingestion/ingestion_service/proto/__init__.py
	@touch services/query/query_service/proto/__init__.py
	@if [ -d "venv" ]; then \
		PYTHON="bash -c 'source venv/bin/activate && python3 -m grpc_tools.protoc'"; \
	fi
	@bash -c "source venv/bin/activate && python3 -m grpc_tools.protoc -I=proto --python_out=services/auth/auth_service/proto --grpc_python_out=services/auth/auth_service/proto --pyi_out=services/auth/auth_service/proto proto/auth.proto"
	@bash -c "source venv/bin/activate && python3 -m grpc_tools.protoc -I=proto --python_out=services/gateway/gateway_service/proto --grpc_python_out=services/gateway/gateway_service/proto --pyi_out=services/gateway/gateway_service/proto proto/auth.proto"
	@bash -c "source venv/bin/activate && python3 -m grpc_tools.protoc -I=proto --python_out=services/ingestion/ingestion_service/proto --grpc_python_out=services/ingestion/ingestion_service/proto --pyi_out=services/ingestion/ingestion_service/proto proto/ingestion.proto"
	@bash -c "source venv/bin/activate && python3 -m grpc_tools.protoc -I=proto --python_out=services/gateway/gateway_service/proto --grpc_python_out=services/gateway/gateway_service/proto --pyi_out=services/gateway/gateway_service/proto proto/ingestion.proto"
	@bash -c "source venv/bin/activate && python3 -m grpc_tools.protoc -I=proto --python_out=services/query/query_service/proto --grpc_python_out=services/query/query_service/proto --pyi_out=services/query/query_service/proto proto/query.proto"
	@bash -c "source venv/bin/activate && python3 -m grpc_tools.protoc -I=proto --python_out=services/gateway/gateway_service/proto --grpc_python_out=services/gateway/gateway_service/proto --pyi_out=services/gateway/gateway_service/proto proto/query.proto"
	@if [ -f "services/auth/auth_service/proto/auth_pb2_grpc.py" ]; then \
		sed -i 's/^import auth_pb2 as auth__pb2/from . import auth_pb2 as auth__pb2/' services/auth/auth_service/proto/auth_pb2_grpc.py; fi
	@if [ -f "services/gateway/gateway_service/proto/auth_pb2_grpc.py" ]; then \
		sed -i 's/^import auth_pb2 as auth__pb2/from . import auth_pb2 as auth__pb2/' services/gateway/gateway_service/proto/auth_pb2_grpc.py; fi
	@if [ -f "services/ingestion/ingestion_service/proto/ingestion_pb2_grpc.py" ]; then \
		sed -i 's/^import ingestion_pb2 as ingestion__pb2/from . import ingestion_pb2 as ingestion__pb2/' services/ingestion/ingestion_service/proto/ingestion_pb2_grpc.py; fi
	@if [ -f "services/gateway/gateway_service/proto/ingestion_pb2_grpc.py" ]; then \
		sed -i 's/^import ingestion_pb2 as ingestion__pb2/from . import ingestion_pb2 as ingestion__pb2/' services/gateway/gateway_service/proto/ingestion_pb2_grpc.py; fi
	@if [ -f "services/query/query_service/proto/query_pb2_grpc.py" ]; then \
		sed -i 's/^import query_pb2 as query__pb2/from . import query_pb2 as query__pb2/' services/query/query_service/proto/query_pb2_grpc.py; fi
	@if [ -f "services/gateway/gateway_service/proto/query_pb2_grpc.py" ]; then \
		sed -i 's/^import query_pb2 as query__pb2/from . import query_pb2 as query__pb2/' services/gateway/gateway_service/proto/query_pb2_grpc.py; fi
	@echo "Protobuf compiled"

# ==================== Dev ====================

.PHONY: up
up:
	docker-compose down --rmi local && docker-compose up -d --build

.PHONY: down
down:
	docker-compose down

# ==================== Testing ====================

.PHONY: test
test: test-auth test-gateway test-ingestion test-analytics test-query test-migrations

.PHONY: test-auth
test-auth:
	@bash -c "source venv/bin/activate && cd services/auth && pytest tests/ -v"

.PHONY: test-gateway
test-gateway:
	@bash -c "source venv/bin/activate && cd services/gateway && pytest tests/ -v"

.PHONY: test-ingestion
test-ingestion:
	@bash -c "source venv/bin/activate && cd services/ingestion && pytest tests/ -v"

.PHONY: test-analytics
test-analytics:
	@bash -c "source venv/bin/activate && cd services/analytics && pytest tests/ -v"

.PHONY: test-query
test-query:
	@bash -c "source venv/bin/activate && cd services/query && pytest tests/ -v"

.PHONY: test-migrations
test-migrations:
	@bash -c "source venv/bin/activate && cd services/migrations && pytest tests/ -v"

# ==================== Database ====================

# .env carries the compose hostnames, which do not resolve from the host, and
# the logs DB is published on 5433 rather than its container port.
DB_ENV := ENV_FILE_PATH=$(CURDIR)/.env AUTH_DB_HOST=localhost AUTH_DB_PORT=5432 LOGS_DB_HOST=localhost LOGS_DB_PORT=5433

.PHONY: db-status
db-status:
	@bash -c "source venv/bin/activate && cd services/migrations && $(DB_ENV) python -m migration_service status $(ARGS)"

.PHONY: db-upgrade
db-upgrade:
	@bash -c "source venv/bin/activate && cd services/migrations && $(DB_ENV) python -m migration_service upgrade $(ARGS)"

.PHONY: db-downgrade
db-downgrade:
	@bash -c "source venv/bin/activate && cd services/migrations && $(DB_ENV) python -m migration_service downgrade $(ARGS)"

.PHONY: db-migrate
db-migrate:
	@bash -c "source venv/bin/activate && cd services/migrations && $(DB_ENV) python -m migration_service revision $(ARGS)"

.PHONY: db-history
db-history:
	@bash -c "source venv/bin/activate && cd services/migrations && $(DB_ENV) python -m migration_service history $(ARGS)"

.PHONY: db-stamp
db-stamp:
	@bash -c "source venv/bin/activate && cd services/migrations && $(DB_ENV) python -m migration_service stamp $(ARGS)"

# ==================== Production ====================

PROD_REGISTRY := container-repository.jtuta.cloud/ledger
PROD_TAG := latest
SERVICES := auth gateway ingestion analytics query migrations

.PHONY: prod-deploy
prod-deploy:
	@for service in $(SERVICES); do \
		echo "Building $$service..."; \
		docker build --file services/$$service/Dockerfile --tag $(PROD_REGISTRY)/$$service:$(PROD_TAG) --platform linux/amd64 services/$$service || exit 1; \
		echo "Pushing $$service..."; \
		docker push $(PROD_REGISTRY)/$$service:$(PROD_TAG) || exit 1; \
	done
	@echo "All production images deployed"

.PHONY: prod-up
prod-up:
	docker-compose -f docker-compose.prod.yaml up -d

.PHONY: prod-down
prod-down:
	docker-compose -f docker-compose.prod.yaml down
