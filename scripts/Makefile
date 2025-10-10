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
	@echo "  logs        - View logs"
	@echo "  restart     - Restart all services"
	@echo "  db-migrate  - Generate new migration"
	@echo "  db-upgrade  - Apply migrations"
	@echo "  db-shell    - Open database shell"
	@echo "  redis-cli   - Open Redis CLI"
	@echo "  test        - Run tests"
	@echo "  clean       - Clean generated files"

# ==================== Setup ====================

.PHONY: setup
setup:
	@if [ ! -f .env ]; then cp .env.example .env; echo "Created .env"; fi
	@if [ ! -d "venv" ]; then \
		echo "Creating virtual environment..."; \
		python3 -m venv venv; \
		echo "Virtual environment created"; \
	fi
	@echo "Activating virtual environment and installing dependencies..."
	@bash -c "source venv/bin/activate && cd services/auth && pip install -r requirements.txt"
	make proto
	@echo "Setup complete! Edit .env if needed, then run 'make up'"

# ==================== Protobuf ====================

.PHONY: proto
proto:
	@echo "Compiling protobuf files..."
	@mkdir -p services/auth/auth_service/proto
	@if [ ! -f "services/auth/auth_service/proto/__init__.py" ]; then \
		touch services/auth/auth_service/proto/__init__.py; \
		echo "Created services/auth/auth_service/proto/__init__.py"; \
	fi
	@if [ -d "venv" ]; then \
		bash -c "source venv/bin/activate && python3 -m grpc_tools.protoc \
			-I=proto \
			--python_out=services/auth/auth_service/proto \
			--grpc_python_out=services/auth/auth_service/proto \
			--pyi_out=services/auth/auth_service/proto \
			proto/auth.proto"; \
	else \
		python3 -m grpc_tools.protoc \
			-I=proto \
			--python_out=services/auth/auth_service/proto \
			--grpc_python_out=services/auth/auth_service/proto \
			--pyi_out=services/auth/auth_service/proto \
			proto/auth.proto; \
	fi
	@echo "Protobuf compiled"
	@if [ -f "services/auth/auth_service/proto/auth_pb2_grpc.py" ]; then \
		sed -i 's/^import auth_pb2 as auth__pb2/from . import auth_pb2 as auth__pb2/' services/auth/auth_service/proto/auth_pb2_grpc.py; \
		echo "Fixed imports in auth_pb2_grpc.py"; \
	fi

# ==================== Docker ====================

.PHONY: up
up:
	docker-compose up -d
	@echo "Services started. Check status with 'make ps'"

.PHONY: down
down:
	docker-compose down

.PHONY: logs
logs:
	docker-compose logs -f auth-service

.PHONY: restart
restart: down up

.PHONY: ps
ps:
	docker-compose ps

.PHONY: build
build:
	docker-compose build

# ==================== Database ====================

.PHONY: db-migrate
db-migrate:
	@if [ ! -d "venv" ]; then \
		echo "Virtual environment not found. Run 'make setup' first."; \
		exit 1; \
	fi
	@read -p "Migration message: " msg; \
	bash -c "source venv/bin/activate && cd services/auth && alembic revision --autogenerate -m \"$$msg\""

.PHONY: db-upgrade
db-upgrade:
	@if [ ! -d "venv" ]; then \
		echo "Virtual environment not found. Run 'make setup' first."; \
		exit 1; \
	fi
	@bash -c "source venv/bin/activate && cd services/auth && alembic upgrade head"

.PHONY: db-shell
db-shell:
	docker-compose exec postgres psql -U $(AUTH_DB_USER) -d $(AUTH_DB_NAME)

# ==================== Redis ====================

.PHONY: redis-cli
redis-cli:
	docker-compose exec redis redis-cli

# ==================== Testing ====================

.PHONY: test
test:
	@if [ ! -d "venv" ]; then \
		echo "Virtual environment not found. Run 'make setup' first."; \
		exit 1; \
	fi
	@bash -c "source venv/bin/activate && cd services/auth && pytest tests/ -v"

# ==================== Development ====================

.PHONY: dev
dev:
	@if [ ! -d "venv" ]; then \
		echo "Virtual environment not found. Run 'make setup' first."; \
		exit 1; \
	fi
	@bash -c "source venv/bin/activate && cd services/auth && python3 -m auth_service.main"

# ==================== Cleanup ====================

.PHONY: clean
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete

.PHONY: clean-all
clean-all: clean down
	docker-compose down -v
	@echo "WARNING: All data deleted!"