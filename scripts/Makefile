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
	@echo "  logs-analytics - View analytics workers logs"
	@echo "  logs-query  - View query service logs"
	@echo "  restart     - Restart all services"
	@echo "  ps          - Show service status"
	@echo "  build       - Build Docker images"
	@echo "  build-auth  - Build auth service image"
	@echo "  build-gateway - Build gateway service image"
	@echo "  build-ingestion - Build ingestion service image"
	@echo "  build-analytics - Build analytics workers image"
	@echo "  build-query - Build query service image"
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
	@echo "  test-analytics - Run analytics workers tests"
	@echo "  test-query  - Run query service tests"
	@echo "  dev-auth    - Run auth service locally"
	@echo "  dev-gateway - Run gateway service locally"
	@echo "  dev-ingestion - Run ingestion service locally"
	@echo "  dev-worker  - Run storage worker locally"
	@echo "  dev-analytics - Run analytics workers locally"
	@echo "  dev-query   - Run query service locally"
	@echo "  clean       - Clean generated files"
	@echo "  clean-all   - Clean everything including Docker volumes"
	@echo ""
	@echo "Production Commands:"
	@echo "  prod-build  - Build production images for GCP"
	@echo "  prod-push   - Push production images to GCP Artifact Registry"
	@echo "  prod-deploy - Build and push production images"
	@echo "  prod-up     - Start services using production images"
	@echo "  prod-down   - Stop production services"

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
		cd ../ingestion && pip install -r requirements.txt && \
		cd ../analytics && pip install -r requirements.txt"
	make proto
	@echo "Setup complete! Edit .env if needed, then run 'make up'"

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
		bash -c "source venv/bin/activate && python3 -m grpc_tools.protoc \
			-I=proto \
			--python_out=services/query/query_service/proto \
			--grpc_python_out=services/query/query_service/proto \
			--pyi_out=services/query/query_service/proto \
			proto/query.proto"; \
		bash -c "source venv/bin/activate && python3 -m grpc_tools.protoc \
			-I=proto \
			--python_out=services/gateway/gateway_service/proto \
			--grpc_python_out=services/gateway/gateway_service/proto \
			--pyi_out=services/gateway/gateway_service/proto \
			proto/query.proto"; \
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
		python3 -m grpc_tools.protoc \
			-I=proto \
			--python_out=services/query/query_service/proto \
			--grpc_python_out=services/query/query_service/proto \
			--pyi_out=services/query/query_service/proto \
			proto/query.proto; \
		python3 -m grpc_tools.protoc \
			-I=proto \
			--python_out=services/gateway/gateway_service/proto \
			--grpc_python_out=services/gateway/gateway_service/proto \
			--pyi_out=services/gateway/gateway_service/proto \
			proto/query.proto; \
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
	@if [ -f "services/query/query_service/proto/query_pb2_grpc.py" ]; then \
		sed -i 's/^import query_pb2 as query__pb2/from . import query_pb2 as query__pb2/' services/query/query_service/proto/query_pb2_grpc.py; \
		echo "Fixed imports in query service"; \
	fi
	@if [ -f "services/gateway/gateway_service/proto/query_pb2_grpc.py" ]; then \
		sed -i 's/^import query_pb2 as query__pb2/from . import query_pb2 as query__pb2/' services/gateway/gateway_service/proto/query_pb2_grpc.py; \
		echo "Fixed imports in gateway service (query)"; \
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

.PHONY: logs-analytics
logs-analytics:
	docker-compose logs -f analytics-workers

.PHONY: logs-query
logs-query:
	docker-compose logs -f query

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

.PHONY: build-analytics
build-analytics:
	docker-compose build analytics-workers

.PHONY: build-query
build-query:
	docker-compose build query

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
test: test-auth test-gateway test-ingestion test-query

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

.PHONY: test-analytics
test-analytics:
	@if [ ! -d "venv" ]; then \
		echo "Virtual environment not found. Run 'make setup' first."; \
		exit 1; \
	fi
	@bash -c "source venv/bin/activate && cd services/analytics && pytest tests/ -v"

.PHONY: test-query
test-query:
	@if [ ! -d "venv" ]; then \
		echo "Virtual environment not found. Run 'make setup' first."; \
		exit 1; \
	fi
	@bash -c "source venv/bin/activate && cd services/query && pytest tests/ -v"

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

.PHONY: dev-analytics
dev-analytics:
	@if [ ! -d "venv" ]; then \
		echo "Virtual environment not found. Run 'make setup' first."; \
		exit 1; \
	fi
	@bash -c "source venv/bin/activate && cd services/analytics && python3 -m analytics_workers.main"

.PHONY: dev-query
dev-query:
	@if [ ! -d "venv" ]; then \
		echo "Virtual environment not found. Run 'make setup' first."; \
		exit 1; \
	fi
	@bash -c "source venv/bin/activate && cd services/query && python3 -m query_service.main"

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

# ==================== Production Deployment ====================

PROD_REGISTRY := europe-central2-docker.pkg.dev/ledger-478119/images
PROD_TAG := latest
SERVICES := auth gateway ingestion analytics query

define check_docker
	@if ! docker version > /dev/null 2>&1; then \
		echo "\033[0;31mDocker is not running or not installed\033[0m"; \
		exit 1; \
	fi
endef

define check_gcloud
	@if ! command -v gcloud > /dev/null 2>&1; then \
		echo "\033[0;31mgcloud CLI is not installed\033[0m"; \
		exit 1; \
	fi
	@if ! gcloud auth print-access-token > /dev/null 2>&1; then \
		echo "\033[0;33mGoogle Cloud authentication required.\033[0m"; \
		echo "\033[0;33mAttempting to authenticate with gcloud...\033[0m"; \
		gcloud auth configure-docker europe-central2-docker.pkg.dev || \
		(echo "\033[0;31mFailed to configure Docker for GCP\033[0m" && \
		 echo "Please run: gcloud auth configure-docker europe-central2-docker.pkg.dev" && \
		 exit 1); \
	fi
endef

define build_service
	@echo ""; \
	echo "======================================================================"; \
	echo "Building $(1) service"; \
	echo "======================================================================"; \
	echo ""; \
	echo "Context: services/$(1)"; \
	echo "Dockerfile: services/$(1)/Dockerfile"; \
	echo "Image: $(PROD_REGISTRY)/$(1):$(PROD_TAG)"; \
	echo ""; \
	if docker build \
		--file services/$(1)/Dockerfile \
		--tag $(PROD_REGISTRY)/$(1):$(PROD_TAG) \
		--platform linux/amd64 \
		services/$(1); then \
		echo "\033[0;32m[SUCCESS] $(1) image built successfully\033[0m"; \
	else \
		echo "\033[0;31m[ERROR] Failed to build $(1) image\033[0m"; \
		exit 1; \
	fi
endef

define push_service
	@echo ""; \
	echo "======================================================================"; \
	echo "Pushing $(1) service"; \
	echo "======================================================================"; \
	echo ""; \
	echo "Image: $(PROD_REGISTRY)/$(1):$(PROD_TAG)"; \
	echo ""; \
	if docker push $(PROD_REGISTRY)/$(1):$(PROD_TAG); then \
		echo "\033[0;32m[SUCCESS] $(1) image pushed successfully\033[0m"; \
	else \
		echo "\033[0;31m[ERROR] Failed to push $(1) image\033[0m"; \
		exit 1; \
	fi
endef

.PHONY: prod-build
prod-build:
	@echo ""
	@echo "======================================================================"
	@echo "Building production images for GCP"
	@echo "======================================================================"
	@echo ""
	@echo "Registry: $(PROD_REGISTRY)"
	@echo "Tag: $(PROD_TAG)"
	$(call check_docker)
	@success=0; \
	total=5; \
	for service in $(SERVICES); do \
		$(call build_service,$$service) && success=$$((success + 1)) || true; \
	done; \
	echo ""; \
	echo "======================================================================"; \
	echo "Summary"; \
	echo "======================================================================"; \
	echo ""; \
	echo "Total services: $$total"; \
	echo "\033[0;32m[SUCCESS] Successful: $$success\033[0m"; \
	if [ $$success -ne $$total ]; then \
		echo "\033[0;31m[ERROR] Failed: $$((total - success))\033[0m"; \
		exit 1; \
	fi; \
	echo ""; \
	echo "\033[0;32m[SUCCESS] All production images built successfully!\033[0m"

.PHONY: prod-push
prod-push:
	@echo ""
	@echo "======================================================================"
	@echo "Pushing production images to GCP Artifact Registry"
	@echo "======================================================================"
	@echo ""
	@echo "Registry: $(PROD_REGISTRY)"
	@echo "Tag: $(PROD_TAG)"
	$(call check_docker)
	$(call check_gcloud)
	@success=0; \
	total=5; \
	for service in $(SERVICES); do \
		$(call push_service,$$service) && success=$$((success + 1)) || true; \
	done; \
	echo ""; \
	echo "======================================================================"; \
	echo "Summary"; \
	echo "======================================================================"; \
	echo ""; \
	echo "Total services: $$total"; \
	echo "\033[0;32m[SUCCESS] Successful: $$success\033[0m"; \
	if [ $$success -ne $$total ]; then \
		echo "\033[0;31m[ERROR] Failed: $$((total - success))\033[0m"; \
		exit 1; \
	fi; \
	echo ""; \
	echo "\033[0;32m[SUCCESS] All production images pushed successfully!\033[0m"; \
	echo ""; \
	echo "\033[0;33mYou can now deploy using:\033[0m"; \
	echo "\033[0;36m  docker-compose -f docker-compose.prod.yaml up -d\033[0m"

.PHONY: prod-deploy
prod-deploy:
	@echo ""
	@echo "======================================================================"
	@echo "Building and pushing production images"
	@echo "======================================================================"
	@echo ""
	@echo "Registry: $(PROD_REGISTRY)"
	@echo "Tag: $(PROD_TAG)"
	$(call check_docker)
	$(call check_gcloud)
	@success=0; \
	total=5; \
	for service in $(SERVICES); do \
		if $(call build_service,$$service); then \
			$(call push_service,$$service) && success=$$((success + 1)) || true; \
		fi; \
	done; \
	echo ""; \
	echo "======================================================================"; \
	echo "Summary"; \
	echo "======================================================================"; \
	echo ""; \
	echo "Total services: $$total"; \
	echo "\033[0;32m[SUCCESS] Successful: $$success\033[0m"; \
	if [ $$success -ne $$total ]; then \
		echo "\033[0;31m[ERROR] Failed: $$((total - success))\033[0m"; \
		exit 1; \
	fi; \
	echo ""; \
	echo "\033[0;32m[SUCCESS] All production images deployed successfully!\033[0m"; \
	echo ""; \
	echo "\033[0;33mNext steps:\033[0m"; \
	echo "  1. Deploy to your production environment"; \
	echo "  2. Or test locally with: \033[0;36mmake prod-up\033[0m"

.PHONY: prod-up
prod-up:
	@echo "Starting services with production images..."
	@docker-compose -f docker-compose.prod.yaml up -d
	@echo "\033[0;32mProduction services started. Check status with 'make ps'\033[0m"

.PHONY: prod-down
prod-down:
	@echo "Stopping production services..."
	@docker-compose -f docker-compose.prod.yaml down
	@echo "\033[0;32mProduction services stopped\033[0m"