# Makefile - Essential commands

include .env
export

.PHONY: help
help:
	@echo "Available commands:"
	@echo "  setup       - Create venv, install deps, compile protos"
	@echo "  proto       - Compile protobuf files"
	@echo "  up          - Start all dev services"
	@echo "  down        - Stop all dev services"
	@echo "  build       - Build dev Docker images"
	@echo "  redeploy    - Stop, rebuild and start dev services"
	@echo "  test        - Run all tests"
	@echo "  test-auth   - Run auth service tests"
	@echo "  test-gateway - Run gateway service tests"
	@echo "  test-ingestion - Run ingestion service tests"
	@echo "  test-analytics - Run analytics workers tests"
	@echo "  test-query  - Run query service tests"
	@echo ""
	@echo "Production Commands:"
	@echo "  prod-build  - Build production images for registry"
	@echo "  prod-push   - Push production images to registry"
	@echo "  prod-deploy - Build and push production images"
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
		cd ../query && pip install -r requirements.txt"
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
	docker-compose up -d

.PHONY: down
down:
	docker-compose down

.PHONY: build
build:
	docker-compose build

.PHONY: redeploy
redeploy: down build up

# ==================== Testing ====================

.PHONY: test
test: test-auth test-gateway test-ingestion test-analytics test-query

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

# ==================== Production ====================

PROD_REGISTRY := container-repository.jtuta.cloud/ledger
PROD_TAG := latest
SERVICES := auth gateway ingestion analytics query

.PHONY: prod-build
prod-build:
	@for service in $(SERVICES); do \
		echo "Building $$service..."; \
		docker build --file services/$$service/Dockerfile --tag $(PROD_REGISTRY)/$$service:$(PROD_TAG) --platform linux/amd64 services/$$service || exit 1; \
	done
	@echo "All production images built"

.PHONY: prod-push
prod-push:
	@for service in $(SERVICES); do \
		echo "Pushing $$service..."; \
		docker push $(PROD_REGISTRY)/$$service:$(PROD_TAG) || exit 1; \
	done
	@echo "All production images pushed"

.PHONY: prod-deploy
prod-deploy: prod-build prod-push

.PHONY: prod-up
prod-up:
	docker-compose -f docker-compose.prod.yaml up -d

.PHONY: prod-down
prod-down:
	docker-compose -f docker-compose.prod.yaml down
