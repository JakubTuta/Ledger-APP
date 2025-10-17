# Makefile - Essential commands

include .env
export

.PHONY: help
help:
	@echo "Available commands:"
	@echo "  setup       - Initial setup (copy .env, install deps, compile protos)"
	@echo "  proto       - Compile protobuf files"
	@echo "  up          - Start all services"
	@echo "  down        - Stop all services"
	@echo "  logs        - View logs (default: all services)"
	@echo "  logs-auth   - View auth service logs"
	@echo "  logs-gateway - View gateway service logs"
	@echo "  logs-ingestion - View ingestion service logs"
	@echo "  logs-worker - View worker logs"
	@echo "  restart     - Restart all services"
	@echo "  ps          - Show service status"
	@echo "  build       - Build Docker images"
	@echo "  db-migrate  - Generate new auth DB migration"
	@echo "  db-upgrade  - Apply auth DB migrations"
	@echo "  db-shell    - Open auth database shell"
	@echo "  logs-db-migrate - Generate new logs DB migration"
	@echo "  logs-db-upgrade - Apply logs DB migrations"
	@echo "  logs-db-shell - Open logs database shell"
	@echo "  redis-cli   - Open Redis CLI"
	@echo "  test        - Run all tests"
	@echo "  test-auth   - Run auth service tests"
	@echo "  test-gateway - Run gateway service tests"
	@echo "  test-ingestion - Run ingestion service tests"
	@echo "  dev-auth    - Run auth service locally"
	@echo "  dev-gateway - Run gateway service locally"
	@echo "  dev-ingestion - Run ingestion service locally"
	@echo "  dev-worker  - Run storage worker locally"
	@echo "  clean       - Clean generated files"
	@echo "  clean-all   - Clean everything including Docker volumes"

# ==================== Setup ====================

.PHONY: setup
setup:
	@if [ ! -f .env ]; then cp .env.example .env; echo "Created .env"; fi
	@if [ ! -d "venv" ]; then \
		echo "Creating virtual environment..."; \
		python3 -m venv venv; \
		echo "Virtual environment created"; \
	fi
	@echo "Installing dependencies..."
	@bash -c "source venv/bin/activate && \
		cd services/auth && pip install -r requirements.txt && \
		cd ../gateway && pip install -r requirements.txt && \
		cd ../ingestion && pip install -r requirements.txt"
	make proto
	@echo "Setup complete! Edit .env if needed, then run 'make up'"

# ==================== Protobuf ====================

.PHONY: proto
proto:
	@echo "Compiling protobuf files..."
	@mkdir -p services/auth/auth_service/proto
	@mkdir -p services/gateway/gateway_service/proto
	@mkdir -p services/ingestion/ingestion_service/proto
	@touch services/auth/auth_service/proto/__init__.py
	@touch services/gateway/gateway_service/proto/__init__.py
	@touch services/ingestion/ingestion_service/proto/__init__.py
	@if [ -d "venv" ]; then \
		bash -c "source venv/bin/activate && python3 -m grpc_tools.protoc \
			-I=proto \
			--python_out=services/auth/auth_service/proto \
			--grpc_python_out=services/auth/auth_service/proto \
			--pyi_out=services/auth/auth_service/proto \
			proto/auth.proto"; \
		bash -c "source venv/bin/activate && python3 -m grpc_tools.protoc \
			-I=proto \
			--python_out=services/gateway/gateway_service/proto \
			--grpc_python_out=services/gateway/gateway_service/proto \
			--pyi_out=services/gateway/gateway_service/proto \
			proto/auth.proto"; \
		bash -c "source venv/bin/activate && python3 -m grpc_tools.protoc \
			-I=proto \
			--python_out=services/ingestion/ingestion_service/proto \
			--grpc_python_out=services/ingestion/ingestion_service/proto \
			--pyi_out=services/ingestion/ingestion_service/proto \
			proto/ingestion.proto"; \
		bash -c "source venv/bin/activate && python3 -m grpc_tools.protoc \
			-I=proto \
			--python_out=services/gateway/gateway_service/proto \
			--grpc_python_out=services/gateway/gateway_service/proto \
			--pyi_out=services/gateway/gateway_service/proto \
			proto/ingestion.proto"; \
	else \
		python3 -m grpc_tools.protoc \
			-I=proto \
			--python_out=services/auth/auth_service/proto \
			--grpc_python_out=services/auth/auth_service/proto \
			--pyi_out=services/auth/auth_service/proto \
			proto/auth.proto; \
		python3 -m grpc_tools.protoc \
			-I=proto \
			--python_out=services/gateway/gateway_service/proto \
			--grpc_python_out=services/gateway/gateway_service/proto \
			--pyi_out=services/gateway/gateway_service/proto \
			proto/auth.proto; \
		python3 -m grpc_tools.protoc \
			-I=proto \
			--python_out=services/ingestion/ingestion_service/proto \
			--grpc_python_out=services/ingestion/ingestion_service/proto \
			--pyi_out=services/ingestion/ingestion_service/proto \
			proto/ingestion.proto; \
		python3 -m grpc_tools.protoc \
			-I=proto \
			--python_out=services/gateway/gateway_service/proto \
			--grpc_python_out=services/gateway/gateway_service/proto \
			--pyi_out=services/gateway/gateway_service/proto \
			proto/ingestion.proto; \
	fi
	@echo "Protobuf compiled"
	@if [ -f "services/auth/auth_service/proto/auth_pb2_grpc.py" ]; then \
		sed -i 's/^import auth_pb2 as auth__pb2/from . import auth_pb2 as auth__pb2/' services/auth/auth_service/proto/auth_pb2_grpc.py; \
		echo "Fixed imports in auth service"; \
	fi
	@if [ -f "services/gateway/gateway_service/proto/auth_pb2_grpc.py" ]; then \
		sed -i 's/^import auth_pb2 as auth__pb2/from . import auth_pb2 as auth__pb2/' services/gateway/gateway_service/proto/auth_pb2_grpc.py; \
		echo "Fixed imports in gateway service"; \
	fi
	@if [ -f "services/ingestion/ingestion_service/proto/ingestion_pb2_grpc.py" ]; then \
		sed -i 's/^import ingestion_pb2 as ingestion__pb2/from . import ingestion_pb2 as ingestion__pb2/' services/ingestion/ingestion_service/proto/ingestion_pb2_grpc.py; \
		echo "Fixed imports in ingestion service"; \
	fi
	@if [ -f "services/gateway/gateway_service/proto/ingestion_pb2_grpc.py" ]; then \
		sed -i 's/^import ingestion_pb2 as ingestion__pb2/from . import ingestion_pb2 as ingestion__pb2/' services/gateway/gateway_service/proto/ingestion_pb2_grpc.py; \
		echo "Fixed imports in gateway service (ingestion)"; \
	fi

# ==================== Docker ====================

.PHONY: up
up:
	docker-compose up -d
	@echo "Services started. Check status with 'make ps'"
	@echo "Gateway API: http://localhost:$(GATEWAY_HTTP_PORT)"
	@echo "Auth gRPC: localhost:$(AUTH_GRPC_PORT)"

.PHONY: down
down:
	docker-compose down

.PHONY: logs
logs:
	docker-compose logs -f

.PHONY: logs-auth
logs-auth:
	docker-compose logs -f auth-service

.PHONY: logs-gateway
logs-gateway:
	docker-compose logs -f gateway

.PHONY: logs-ingestion
logs-ingestion:
	docker-compose logs -f ingestion

.PHONY: logs-worker
logs-worker:
	docker-compose logs -f ingestion-worker

.PHONY: restart
restart: down up

.PHONY: ps
ps:
	docker-compose ps

.PHONY: build
build:
	docker-compose build

.PHONY: build-auth
build-auth:
	docker-compose build auth-service

.PHONY: build-gateway
build-gateway:
	docker-compose build gateway

.PHONY: build-ingestion
build-ingestion:
	docker-compose build ingestion ingestion-worker

# ==================== Database (Auth) ====================

.PHONY: db-migrate
db-migrate:
	@if [ ! -d "venv" ]; then \
		echo "Virtual environment not found. Run 'make setup' first."; \
		exit 1; \
	fi
	@read -p "Migration message: " msg; \
	bash -c "source venv/bin/activate && cd services/auth && alembic revision --autogenerate -m \"$msg\""

.PHONY: db-upgrade
db-upgrade:
	@if [ ! -d "venv" ]; then \
		echo "Virtual environment not found. Run 'make setup' first."; \
		exit 1; \
	fi
	@bash -c "source venv/bin/activate && cd services/auth && alembic upgrade head"

.PHONY: db-downgrade
db-downgrade:
	@if [ ! -d "venv" ]; then \
		echo "Virtual environment not found. Run 'make setup' first."; \
		exit 1; \
	fi
	@bash -c "source venv/bin/activate && cd services/auth && alembic downgrade -1"

.PHONY: db-shell
db-shell:
	docker-compose exec postgres psql -U $(AUTH_DB_USER) -d $(AUTH_DB_NAME)

# ==================== Database (Logs) ====================

.PHONY: logs-db-migrate
logs-db-migrate:
	@if [ ! -d "venv" ]; then \
		echo "Virtual environment not found. Run 'make setup' first."; \
		exit 1; \
	fi
	@read -p "Migration message: " msg; \
	bash -c "source venv/bin/activate && cd services/ingestion && alembic revision --autogenerate -m \"$$msg\""

.PHONY: logs-db-upgrade
logs-db-upgrade:
	@if [ ! -d "venv" ]; then \
		echo "Virtual environment not found. Run 'make setup' first."; \
		exit 1; \
	fi
	@bash -c "source venv/bin/activate && cd services/ingestion && alembic upgrade head"

.PHONY: logs-db-downgrade
logs-db-downgrade:
	@if [ ! -d "venv" ]; then \
		echo "Virtual environment not found. Run 'make setup' first."; \
		exit 1; \
	fi
	@bash -c "source venv/bin/activate && cd services/ingestion && alembic downgrade -1"

.PHONY: logs-db-shell
logs-db-shell:
	docker-compose exec postgres-logs psql -U $(LOGS_DB_USER) -d $(LOGS_DB_NAME)

# ==================== Redis ====================

.PHONY: redis-cli
redis-cli:
	docker-compose exec redis redis-cli -a $(REDIS_PASSWORD)

.PHONY: redis-flush
redis-flush:
	docker-compose exec redis redis-cli -a $(REDIS_PASSWORD) FLUSHALL

# ==================== Testing ====================

.PHONY: test
test: test-auth test-gateway test-ingestion

.PHONY: test-auth
test-auth:
	@if [ ! -d "venv" ]; then \
		echo "Virtual environment not found. Run 'make setup' first."; \
		exit 1; \
	fi
	@bash -c "source venv/bin/activate && cd services/auth && pytest tests/ -v"

.PHONY: test-gateway
test-gateway:
	@if [ ! -d "venv" ]; then \
		echo "Virtual environment not found. Run 'make setup' first."; \
		exit 1; \
	fi
	@bash -c "source venv/bin/activate && cd services/gateway && pytest tests/ -v"

.PHONY: test-ingestion
test-ingestion:
	@if [ ! -d "venv" ]; then \
		echo "Virtual environment not found. Run 'make setup' first."; \
		exit 1; \
	fi
	@bash -c "source venv/bin/activate && cd services/ingestion && pytest tests/ -v"

# ==================== Development ====================

.PHONY: dev-auth
dev-auth:
	@if [ ! -d "venv" ]; then \
		echo "Virtual environment not found. Run 'make setup' first."; \
		exit 1; \
	fi
	@bash -c "source venv/bin/activate && cd services/auth && python3 -m auth_service.main"

.PHONY: dev-gateway
dev-gateway:
	@if [ ! -d "venv" ]; then \
		echo "Virtual environment not found. Run 'make setup' first."; \
		exit 1; \
	fi
	@bash -c "source venv/bin/activate && cd services/gateway && uvicorn gateway_service.main:app --reload --port $(GATEWAY_HTTP_PORT)"

.PHONY: dev-ingestion
dev-ingestion:
	@if [ ! -d "venv" ]; then \
		echo "Virtual environment not found. Run 'make setup' first."; \
		exit 1; \
	fi
	@bash -c "source venv/bin/activate && cd services/ingestion && uvicorn ingestion_service.main:app --reload --port $(INGESTION_HTTP_PORT)"

.PHONY: dev-worker
dev-worker:
	@if [ ! -d "venv" ]; then \
		echo "Virtual environment not found. Run 'make setup' first."; \
		exit 1; \
	fi
	@bash -c "source venv/bin/activate && cd services/ingestion && python3 -m ingestion_service.worker"

# ==================== Health Checks ====================

.PHONY: health
health:
	@echo "Checking service health..."
	@curl -s http://localhost:$(GATEWAY_HTTP_PORT)/health | python3 -m json.tool || echo "Gateway: DOWN"
	@curl -s http://localhost:$(GATEWAY_HTTP_PORT)/health/deep | python3 -m json.tool || echo "Deep health: DOWN"

# ==================== Cleanup ====================

.PHONY: clean
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true

.PHONY: clean-all
clean-all: clean down
	docker-compose down -v
	@echo "WARNING: All data deleted!"

# ==================== Load Testing ====================

.PHONY: load-test
load-test:
	@if [ ! -d "venv" ]; then \
		echo "Virtual environment not found. Run 'make setup' first."; \
		exit 1; \
	fi
	@bash -c "source venv/bin/activate && locust -f services/gateway/tests/locustfile.py --host http://localhost:$(GATEWAY_HTTP_PORT)"