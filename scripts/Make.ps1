# Make.ps1 - PowerShell build script for Windows
# Usage: .\Make.ps1 <command>
# Example: .\Make.ps1 help

param(
    [Parameter(Position=0)]
    [string]$Command = "help"
)

# Load environment variables from .env file if it exists
function Load-EnvFile {
    if (Test-Path .env) {
        Get-Content .env | ForEach-Object {
            if ($_ -match '^\s*([^#][^=]*)\s*=\s*(.*)$') {
                $name = $matches[1].Trim()
                $value = $matches[2].Trim()
                [Environment]::SetEnvironmentVariable($name, $value, "Process")
            }
        }
    }
}

# Check and create virtual environment if needed
function Ensure-VirtualEnvironment {
    if (-not (Test-Path "venv")) {
        Write-Host "Creating virtual environment..." -ForegroundColor Cyan
        python -m venv venv
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Virtual environment created" -ForegroundColor Green
        } else {
            Write-Host "Failed to create virtual environment" -ForegroundColor Red
            exit 1
        }
    }
}

# Activate virtual environment and return the python executable path
function Get-VenvPython {
    $venvPython = Join-Path $PWD "venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        return $venvPython
    }
    return "python"
}

# Get pip executable path from venv
function Get-VenvPip {
    $venvPip = Join-Path $PWD "venv\Scripts\pip.exe"
    if (Test-Path $venvPip) {
        return $venvPip
    }
    return "pip"
}

Load-EnvFile

# ==================== Command Functions ====================

function Show-Help {
    Write-Host "Available commands:" -ForegroundColor Cyan
    Write-Host "  help         - Show this help message"
    Write-Host "  setup        - Initial setup (copy .env, install deps, compile protos)"
    Write-Host "  proto        - Compile protobuf files"
    Write-Host "  up           - Start all services"
    Write-Host "  down         - Stop all services"
    Write-Host "  logs         - View logs (default: all services)"
    Write-Host "  logs-auth    - View auth service logs"
    Write-Host "  logs-gateway - View gateway service logs"
    Write-Host "  logs-ingestion - View ingestion service logs"
    Write-Host "  logs-worker  - View worker logs"
    Write-Host "  logs-analytics - View analytics workers logs"
    Write-Host "  restart      - Restart all services"
    Write-Host "  ps           - Show service status"
    Write-Host "  build        - Build Docker images"
    Write-Host "  build-auth   - Build auth service image"
    Write-Host "  build-gateway - Build gateway service image"
    Write-Host "  build-ingestion - Build ingestion service image"
    Write-Host "  build-analytics - Build analytics workers image"
    Write-Host "  db-migrate   - Generate new auth DB migration"
    Write-Host "  db-upgrade   - Apply auth DB migrations"
    Write-Host "  db-downgrade - Rollback last auth DB migration"
    Write-Host "  db-shell     - Open auth database shell"
    Write-Host "  logs-db-migrate - Generate new logs DB migration"
    Write-Host "  logs-db-upgrade - Apply logs DB migrations"
    Write-Host "  logs-db-downgrade - Rollback last logs DB migration"
    Write-Host "  logs-db-shell - Open logs database shell"
    Write-Host "  redis-cli    - Open Redis CLI"
    Write-Host "  redis-flush  - Flush all Redis data"
    Write-Host "  test         - Run all tests"
    Write-Host "  test-auth    - Run auth service tests"
    Write-Host "  test-gateway - Run gateway service tests"
    Write-Host "  test-ingestion - Run ingestion service tests"
    Write-Host "  test-analytics - Run analytics workers tests"
    Write-Host "  test-query   - Run query service tests"
    Write-Host "  dev-auth     - Run auth service locally"
    Write-Host "  dev-gateway  - Run gateway service locally"
    Write-Host "  dev-ingestion - Run ingestion service locally"
    Write-Host "  dev-worker   - Run storage worker locally"
    Write-Host "  dev-analytics - Run analytics workers locally"
    Write-Host "  health       - Check service health"
    Write-Host "  clean        - Clean generated files"
    Write-Host "  clean-all    - Clean everything including Docker volumes"
    Write-Host "  load-test    - Run load tests with Locust"
    Write-Host ""
    Write-Host "Usage: .\Make.ps1 <command>" -ForegroundColor Yellow
}

function Setup {
    Write-Host "Running setup..." -ForegroundColor Cyan
    
    # Copy .env.example to .env if it doesn't exist
    if (-not (Test-Path .env)) {
        Copy-Item .env.example .env
        Write-Host "Created .env" -ForegroundColor Green
    } else {
        Write-Host ".env already exists" -ForegroundColor Yellow
    }
    
    # Ensure virtual environment exists
    Ensure-VirtualEnvironment
    
    # Install Python dependencies
    Write-Host "Installing Python dependencies..." -ForegroundColor Cyan
    $pip = Get-VenvPip
    Push-Location services\auth
    & $pip install -r requirements.txt
    Pop-Location
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Failed to install auth dependencies" -ForegroundColor Red
        exit 1
    }
    
    Push-Location services\gateway
    & $pip install -r requirements.txt
    Pop-Location

    if ($LASTEXITCODE -ne 0) {
        Write-Host "Failed to install gateway dependencies" -ForegroundColor Red
        exit 1
    }

    Push-Location services\ingestion
    & $pip install -r requirements.txt
    Pop-Location

    if ($LASTEXITCODE -ne 0) {
        Write-Host "Failed to install ingestion dependencies" -ForegroundColor Red
        exit 1
    }

    # Compile protobuf files
    Compile-Proto
    
    Write-Host "Setup complete! Edit .env if needed, then run '.\Make.ps1 up'" -ForegroundColor Green
}

function Compile-Proto {
    Write-Host "Compiling protobuf files..." -ForegroundColor Cyan

    # Create proto directories
    $protoDirs = @(
        "services\auth\auth_service\proto",
        "services\gateway\gateway_service\proto",
        "services\ingestion\ingestion_service\proto",
        "services\query\query_service\proto"
    )

    foreach ($dir in $protoDirs) {
        if (-not (Test-Path $dir)) {
            New-Item -ItemType Directory -Path $dir -Force | Out-Null
        }
        $initFile = Join-Path $dir "__init__.py"
        if (-not (Test-Path $initFile)) {
            New-Item -ItemType File -Path $initFile -Force | Out-Null
        }
    }

    $python = Get-VenvPython

    # Compile auth.proto for auth service
    & $python -m grpc_tools.protoc -I=proto --python_out=services/auth/auth_service/proto --grpc_python_out=services/auth/auth_service/proto --pyi_out=services/auth/auth_service/proto proto/auth.proto
    if ($LASTEXITCODE -ne 0) { Write-Host "Auth service proto compilation failed" -ForegroundColor Red; exit 1 }

    # Compile auth.proto for gateway
    & $python -m grpc_tools.protoc -I=proto --python_out=services/gateway/gateway_service/proto --grpc_python_out=services/gateway/gateway_service/proto --pyi_out=services/gateway/gateway_service/proto proto/auth.proto
    if ($LASTEXITCODE -ne 0) { Write-Host "Gateway auth proto compilation failed" -ForegroundColor Red; exit 1 }

    # Compile ingestion.proto for ingestion service
    & $python -m grpc_tools.protoc -I=proto --python_out=services/ingestion/ingestion_service/proto --grpc_python_out=services/ingestion/ingestion_service/proto --pyi_out=services/ingestion/ingestion_service/proto proto/ingestion.proto
    if ($LASTEXITCODE -ne 0) { Write-Host "Ingestion service proto compilation failed" -ForegroundColor Red; exit 1 }

    # Compile ingestion.proto for gateway
    & $python -m grpc_tools.protoc -I=proto --python_out=services/gateway/gateway_service/proto --grpc_python_out=services/gateway/gateway_service/proto --pyi_out=services/gateway/gateway_service/proto proto/ingestion.proto
    if ($LASTEXITCODE -ne 0) { Write-Host "Gateway ingestion proto compilation failed" -ForegroundColor Red; exit 1 }

    # Compile query.proto for query service
    & $python -m grpc_tools.protoc -I=proto --python_out=services/query/query_service/proto --grpc_python_out=services/query/query_service/proto --pyi_out=services/query/query_service/proto proto/query.proto
    if ($LASTEXITCODE -ne 0) { Write-Host "Query service proto compilation failed" -ForegroundColor Red; exit 1 }

    # Compile query.proto for gateway
    & $python -m grpc_tools.protoc -I=proto --python_out=services/gateway/gateway_service/proto --grpc_python_out=services/gateway/gateway_service/proto --pyi_out=services/gateway/gateway_service/proto proto/query.proto
    if ($LASTEXITCODE -ne 0) { Write-Host "Gateway query proto compilation failed" -ForegroundColor Red; exit 1 }

    Write-Host "Protobuf compiled" -ForegroundColor Green

    # Fix imports using relative imports
    $fixImports = @(
        @{ File = "services\auth\auth_service\proto\auth_pb2_grpc.py"; Pattern = "import auth_pb2 as auth__pb2"; Replacement = "from . import auth_pb2 as auth__pb2"; Name = "auth service" },
        @{ File = "services\gateway\gateway_service\proto\auth_pb2_grpc.py"; Pattern = "import auth_pb2 as auth__pb2"; Replacement = "from . import auth_pb2 as auth__pb2"; Name = "gateway (auth)" },
        @{ File = "services\ingestion\ingestion_service\proto\ingestion_pb2_grpc.py"; Pattern = "import ingestion_pb2 as ingestion__pb2"; Replacement = "from . import ingestion_pb2 as ingestion__pb2"; Name = "ingestion service" },
        @{ File = "services\gateway\gateway_service\proto\ingestion_pb2_grpc.py"; Pattern = "import ingestion_pb2 as ingestion__pb2"; Replacement = "from . import ingestion_pb2 as ingestion__pb2"; Name = "gateway (ingestion)" },
        @{ File = "services\query\query_service\proto\query_pb2_grpc.py"; Pattern = "import query_pb2 as query__pb2"; Replacement = "from . import query_pb2 as query__pb2"; Name = "query service" },
        @{ File = "services\gateway\gateway_service\proto\query_pb2_grpc.py"; Pattern = "import query_pb2 as query__pb2"; Replacement = "from . import query_pb2 as query__pb2"; Name = "gateway (query)" }
    )

    foreach ($fix in $fixImports) {
        if (Test-Path $fix.File) {
            $content = Get-Content $fix.File -Raw
            $content = $content -replace [regex]::Escape($fix.Pattern), $fix.Replacement
            Set-Content $fix.File -Value $content -NoNewline
            Write-Host "Fixed imports in $($fix.Name)" -ForegroundColor Green
        }
    }
}

function Start-Services {
    Write-Host "Starting services..." -ForegroundColor Cyan
    docker-compose up -d
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Services started. Check status with '.\Make.ps1 ps'" -ForegroundColor Green
    } else {
        Write-Host "Failed to start services" -ForegroundColor Red
        exit 1
    }
}

function Stop-Services {
    Write-Host "Stopping services..." -ForegroundColor Cyan
    docker-compose down
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Services stopped" -ForegroundColor Green
    } else {
        Write-Host "Failed to stop services" -ForegroundColor Red
        exit 1
    }
}

function Show-Logs {
    Write-Host "Showing logs (Ctrl+C to exit)..." -ForegroundColor Cyan
    docker-compose logs -f
}

function Show-AuthLogs {
    Write-Host "Showing auth service logs (Ctrl+C to exit)..." -ForegroundColor Cyan
    docker-compose logs -f auth-service
}

function Show-GatewayLogs {
    Write-Host "Showing gateway service logs (Ctrl+C to exit)..." -ForegroundColor Cyan
    docker-compose logs -f gateway
}

function Show-IngestionLogs {
    Write-Host "Showing ingestion service logs (Ctrl+C to exit)..." -ForegroundColor Cyan
    docker-compose logs -f ingestion
}

function Show-WorkerLogs {
    Write-Host "Showing storage worker logs (Ctrl+C to exit)..." -ForegroundColor Cyan
    docker-compose logs -f ingestion-worker
}

function Show-AnalyticsLogs {
    Write-Host "Showing analytics workers logs (Ctrl+C to exit)..." -ForegroundColor Cyan
    docker-compose logs -f analytics-workers
}

function Show-QueryLogs {
    Write-Host "Showing query service logs (Ctrl+C to exit)..." -ForegroundColor Cyan
    docker-compose logs -f query
}

function Restart-Services {
    Write-Host "Restarting services..." -ForegroundColor Cyan
    Stop-Services
    Start-Services
}

function Show-Status {
    Write-Host "Service status:" -ForegroundColor Cyan
    docker-compose ps
}

function Build-Images {
    Write-Host "Building Docker images..." -ForegroundColor Cyan
    docker-compose build
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Build complete" -ForegroundColor Green
    } else {
        Write-Host "Build failed" -ForegroundColor Red
        exit 1
    }
}

function Build-AuthImage {
    Write-Host "Building auth service Docker image..." -ForegroundColor Cyan
    docker-compose build auth-service
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Auth service build complete" -ForegroundColor Green
    } else {
        Write-Host "Auth service build failed" -ForegroundColor Red
        exit 1
    }
}

function Build-GatewayImage {
    Write-Host "Building gateway service Docker image..." -ForegroundColor Cyan
    docker-compose build gateway

    if ($LASTEXITCODE -eq 0) {
        Write-Host "Gateway service build complete" -ForegroundColor Green
    } else {
        Write-Host "Gateway service build failed" -ForegroundColor Red
        exit 1
    }
}

function Build-IngestionImage {
    Write-Host "Building ingestion service Docker images..." -ForegroundColor Cyan
    docker-compose build ingestion ingestion-worker

    if ($LASTEXITCODE -eq 0) {
        Write-Host "Ingestion service build complete" -ForegroundColor Green
    } else {
        Write-Host "Ingestion service build failed" -ForegroundColor Red
        exit 1
    }
}

function Build-AnalyticsImage {
    Write-Host "Building analytics workers Docker image..." -ForegroundColor Cyan
    docker-compose build analytics-workers

    if ($LASTEXITCODE -eq 0) {
        Write-Host "Analytics workers build complete" -ForegroundColor Green
    } else {
        Write-Host "Analytics workers build failed" -ForegroundColor Red
        exit 1
    }
}

function Build-QueryImage {
    Write-Host "Building query service Docker image..." -ForegroundColor Cyan
    docker-compose build query

    if ($LASTEXITCODE -eq 0) {
        Write-Host "Query service build complete" -ForegroundColor Green
    } else {
        Write-Host "Query service build failed" -ForegroundColor Red
        exit 1
    }
}

function Create-Migration {
    if (-not (Test-Path "venv")) {
        Write-Host "Virtual environment not found. Run '.\Make.ps1 setup' first." -ForegroundColor Red
        exit 1
    }
    
    $message = Read-Host "Migration message"
    
    if ([string]::IsNullOrWhiteSpace($message)) {
        Write-Host "Migration message cannot be empty" -ForegroundColor Red
        exit 1
    }
    
    Write-Host "Creating migration: $message" -ForegroundColor Cyan
    $python = Get-VenvPython
    Push-Location services\auth
    & $python -m alembic revision --autogenerate -m $message
    Pop-Location
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Migration created" -ForegroundColor Green
    } else {
        Write-Host "Failed to create migration" -ForegroundColor Red
        exit 1
    }
}

function Apply-Migrations {
    if (-not (Test-Path "venv")) {
        Write-Host "Virtual environment not found. Run '.\Make.ps1 setup' first." -ForegroundColor Red
        exit 1
    }
    
    Write-Host "Applying migrations..." -ForegroundColor Cyan
    $python = Get-VenvPython
    Push-Location services\auth
    & $python -m alembic upgrade head
    Pop-Location
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Migrations applied" -ForegroundColor Green
    } else {
        Write-Host "Failed to apply migrations" -ForegroundColor Red
        exit 1
    }
}

function Downgrade-Migration {
    if (-not (Test-Path "venv")) {
        Write-Host "Virtual environment not found. Run '.\Make.ps1 setup' first." -ForegroundColor Red
        exit 1
    }
    
    Write-Host "Rolling back last migration..." -ForegroundColor Cyan
    $python = Get-VenvPython
    Push-Location services\auth
    & $python -m alembic downgrade -1
    Pop-Location
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Migration rolled back" -ForegroundColor Green
    } else {
        Write-Host "Failed to rollback migration" -ForegroundColor Red
        exit 1
    }
}

function Open-DatabaseShell {
    Load-EnvFile
    $dbUser = $env:AUTH_DB_USER
    $dbName = $env:AUTH_DB_NAME

    Write-Host "Opening database shell..." -ForegroundColor Cyan
    docker-compose exec postgres psql -U $dbUser -d $dbName
}

function Create-LogsMigration {
    if (-not (Test-Path "venv")) {
        Write-Host "Virtual environment not found. Run '.\Make.ps1 setup' first." -ForegroundColor Red
        exit 1
    }

    $message = Read-Host "Migration message"

    if ([string]::IsNullOrWhiteSpace($message)) {
        Write-Host "Migration message cannot be empty" -ForegroundColor Red
        exit 1
    }

    Write-Host "Creating logs migration: $message" -ForegroundColor Cyan
    $python = Get-VenvPython
    Push-Location services\ingestion
    & $python -m alembic revision --autogenerate -m $message
    Pop-Location

    if ($LASTEXITCODE -eq 0) {
        Write-Host "Logs migration created" -ForegroundColor Green
    } else {
        Write-Host "Failed to create logs migration" -ForegroundColor Red
        exit 1
    }
}

function Apply-LogsMigrations {
    if (-not (Test-Path "venv")) {
        Write-Host "Virtual environment not found. Run '.\Make.ps1 setup' first." -ForegroundColor Red
        exit 1
    }

    Write-Host "Applying logs migrations..." -ForegroundColor Cyan
    $python = Get-VenvPython
    Push-Location services\ingestion
    & $python -m alembic upgrade head
    Pop-Location

    if ($LASTEXITCODE -eq 0) {
        Write-Host "Logs migrations applied" -ForegroundColor Green
    } else {
        Write-Host "Failed to apply logs migrations" -ForegroundColor Red
        exit 1
    }
}

function Downgrade-LogsMigration {
    if (-not (Test-Path "venv")) {
        Write-Host "Virtual environment not found. Run '.\Make.ps1 setup' first." -ForegroundColor Red
        exit 1
    }

    Write-Host "Rolling back last logs migration..." -ForegroundColor Cyan
    $python = Get-VenvPython
    Push-Location services\ingestion
    & $python -m alembic downgrade -1
    Pop-Location

    if ($LASTEXITCODE -eq 0) {
        Write-Host "Logs migration rolled back" -ForegroundColor Green
    } else {
        Write-Host "Failed to rollback logs migration" -ForegroundColor Red
        exit 1
    }
}

function Open-LogsDatabase {
    Load-EnvFile
    $dbUser = $env:LOGS_DB_USER
    $dbName = $env:LOGS_DB_NAME

    Write-Host "Opening logs database shell..." -ForegroundColor Cyan
    docker-compose exec postgres-logs psql -U $dbUser -d $dbName
}

function Open-RedisShell {
    Load-EnvFile
    $redisPassword = $env:REDIS_PASSWORD
    
    Write-Host "Opening Redis CLI..." -ForegroundColor Cyan
    docker-compose exec redis redis-cli -a $redisPassword
}

function Flush-Redis {
    Load-EnvFile
    $redisPassword = $env:REDIS_PASSWORD
    
    Write-Host "WARNING: This will delete all Redis data!" -ForegroundColor Yellow
    $confirmation = Read-Host "Are you sure? (yes/no)"
    
    if ($confirmation -eq "yes") {
        Write-Host "Flushing Redis..." -ForegroundColor Cyan
        docker-compose exec redis redis-cli -a $redisPassword FLUSHALL
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Redis flushed" -ForegroundColor Green
        } else {
            Write-Host "Failed to flush Redis" -ForegroundColor Red
            exit 1
        }
    } else {
        Write-Host "Operation cancelled" -ForegroundColor Yellow
    }
}

function Run-Tests {
    if (-not (Test-Path "venv")) {
        Write-Host "Virtual environment not found. Run '.\Make.ps1 setup' first." -ForegroundColor Red
        exit 1
    }

    Write-Host "Running all tests..." -ForegroundColor Cyan
    $python = Get-VenvPython

    Write-Host "Testing auth service..." -ForegroundColor Cyan
    Push-Location services\auth
    & $python -m pytest tests/ -v
    $authResult = $LASTEXITCODE
    Pop-Location

    Write-Host "Testing gateway service..." -ForegroundColor Cyan
    Push-Location services\gateway
    & $python -m pytest tests/ -v
    $gatewayResult = $LASTEXITCODE
    Pop-Location

    Write-Host "Testing ingestion service..." -ForegroundColor Cyan
    Push-Location services\ingestion
    & $python -m pytest tests/ -v
    $ingestionResult = $LASTEXITCODE
    Pop-Location

    Write-Host "Testing query service..." -ForegroundColor Cyan
    Push-Location services\query
    & $python -m pytest tests/ -v
    $queryResult = $LASTEXITCODE
    Pop-Location

    if ($authResult -eq 0 -and $gatewayResult -eq 0 -and $ingestionResult -eq 0 -and $queryResult -eq 0) {
        Write-Host "All tests passed" -ForegroundColor Green
    } else {
        Write-Host "Some tests failed" -ForegroundColor Red
        exit 1
    }
}

function Run-AuthTests {
    if (-not (Test-Path "venv")) {
        Write-Host "Virtual environment not found. Run '.\Make.ps1 setup' first." -ForegroundColor Red
        exit 1
    }
    
    Write-Host "Running auth service tests..." -ForegroundColor Cyan
    $python = Get-VenvPython
    Push-Location services\auth
    & $python -m pytest tests/ -v
    Pop-Location
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Auth tests passed" -ForegroundColor Green
    } else {
        Write-Host "Auth tests failed" -ForegroundColor Red
        exit 1
    }
}

function Run-GatewayTests {
    if (-not (Test-Path "venv")) {
        Write-Host "Virtual environment not found. Run '.\Make.ps1 setup' first." -ForegroundColor Red
        exit 1
    }

    Write-Host "Running gateway service tests..." -ForegroundColor Cyan
    $python = Get-VenvPython
    Push-Location services\gateway
    & $python -m pytest tests/ -v
    Pop-Location

    if ($LASTEXITCODE -eq 0) {
        Write-Host "Gateway tests passed" -ForegroundColor Green
    } else {
        Write-Host "Gateway tests failed" -ForegroundColor Red
        exit 1
    }
}

function Run-IngestionTests {
    if (-not (Test-Path "venv")) {
        Write-Host "Virtual environment not found. Run '.\Make.ps1 setup' first." -ForegroundColor Red
        exit 1
    }

    Write-Host "Running ingestion service tests..." -ForegroundColor Cyan
    $python = Get-VenvPython
    Push-Location services\ingestion
    & $python -m pytest tests/ -v
    Pop-Location

    if ($LASTEXITCODE -eq 0) {
        Write-Host "Ingestion tests passed" -ForegroundColor Green
    } else {
        Write-Host "Ingestion tests failed" -ForegroundColor Red
        exit 1
    }
}

function Run-AnalyticsTests {
    if (-not (Test-Path "venv")) {
        Write-Host "Virtual environment not found. Run '.\Make.ps1 setup' first." -ForegroundColor Red
        exit 1
    }

    Write-Host "Running analytics workers tests..." -ForegroundColor Cyan
    $python = Get-VenvPython
    Push-Location services\analytics
    & $python -m pytest tests/ -v
    Pop-Location

    if ($LASTEXITCODE -eq 0) {
        Write-Host "Analytics tests passed" -ForegroundColor Green
    } else {
        Write-Host "Analytics tests failed" -ForegroundColor Red
        exit 1
    }
}

function Run-QueryTests {
    if (-not (Test-Path "venv")) {
        Write-Host "Virtual environment not found. Run '.\Make.ps1 setup' first." -ForegroundColor Red
        exit 1
    }

    Write-Host "Running query service tests..." -ForegroundColor Cyan
    $python = Get-VenvPython
    Push-Location services\query
    & $python -m pytest tests/ -v
    Pop-Location

    if ($LASTEXITCODE -eq 0) {
        Write-Host "Query tests passed" -ForegroundColor Green
    } else {
        Write-Host "Query tests failed" -ForegroundColor Red
        exit 1
    }
}

function Run-DevAuth {
    if (-not (Test-Path "venv")) {
        Write-Host "Virtual environment not found. Run '.\Make.ps1 setup' first." -ForegroundColor Red
        exit 1
    }
    
    Write-Host "Running auth service locally..." -ForegroundColor Cyan
    $python = Get-VenvPython
    Push-Location services\auth
    & $python -m auth_service.main
    Pop-Location
}

function Run-DevGateway {
    if (-not (Test-Path "venv")) {
        Write-Host "Virtual environment not found. Run '.\Make.ps1 setup' first." -ForegroundColor Red
        exit 1
    }

    Load-EnvFile
    $port = $env:GATEWAY_HTTP_PORT
    if ([string]::IsNullOrWhiteSpace($port)) {
        $port = "8000"
    }

    Write-Host "Running gateway service locally on port $port..." -ForegroundColor Cyan
    $python = Get-VenvPython
    Push-Location services\gateway
    & $python -m uvicorn gateway_service.main:app --reload --port $port
    Pop-Location
}

function Run-DevIngestion {
    if (-not (Test-Path "venv")) {
        Write-Host "Virtual environment not found. Run '.\Make.ps1 setup' first." -ForegroundColor Red
        exit 1
    }

    Load-EnvFile
    $port = $env:INGESTION_HTTP_PORT
    if ([string]::IsNullOrWhiteSpace($port)) {
        $port = "8001"
    }

    Write-Host "Running ingestion service locally on port $port..." -ForegroundColor Cyan
    $python = Get-VenvPython
    Push-Location services\ingestion
    & $python -m uvicorn ingestion_service.main:app --reload --port $port
    Pop-Location
}

function Run-DevWorker {
    if (-not (Test-Path "venv")) {
        Write-Host "Virtual environment not found. Run '.\Make.ps1 setup' first." -ForegroundColor Red
        exit 1
    }

    Write-Host "Running storage worker locally..." -ForegroundColor Cyan
    $python = Get-VenvPython
    Push-Location services\ingestion
    & $python -m ingestion_service.worker
    Pop-Location
}

function Run-DevAnalytics {
    if (-not (Test-Path "venv")) {
        Write-Host "Virtual environment not found. Run '.\Make.ps1 setup' first." -ForegroundColor Red
        exit 1
    }

    Write-Host "Running analytics workers locally..." -ForegroundColor Cyan
    $python = Get-VenvPython
    Push-Location services\analytics
    & $python -m analytics_workers.main
    Pop-Location
}

function Run-DevQuery {
    if (-not (Test-Path "venv")) {
        Write-Host "Virtual environment not found. Run '.\Make.ps1 setup' first." -ForegroundColor Red
        exit 1
    }

    Write-Host "Running query service locally on port 8004..." -ForegroundColor Cyan
    $python = Get-VenvPython
    Push-Location services\query
    & $python -m query_service.main
    Pop-Location
}

function Check-Health {
    Load-EnvFile
    $port = $env:GATEWAY_HTTP_PORT
    if ([string]::IsNullOrWhiteSpace($port)) {
        $port = "8000"
    }
    
    Write-Host "Checking service health..." -ForegroundColor Cyan
    
    try {
        $response = Invoke-RestMethod -Uri "http://localhost:$port/health" -Method Get -ErrorAction SilentlyContinue
        Write-Host "Gateway Health:" -ForegroundColor Green
        $response | ConvertTo-Json -Depth 10
    } catch {
        Write-Host "Gateway: DOWN" -ForegroundColor Red
    }
    
    try {
        $response = Invoke-RestMethod -Uri "http://localhost:$port/health/deep" -Method Get -ErrorAction SilentlyContinue
        Write-Host "Deep Health:" -ForegroundColor Green
        $response | ConvertTo-Json -Depth 10
    } catch {
        Write-Host "Deep health: DOWN" -ForegroundColor Red
    }
}

function Run-LoadTest {
    if (-not (Test-Path "venv")) {
        Write-Host "Virtual environment not found. Run '.\Make.ps1 setup' first." -ForegroundColor Red
        exit 1
    }
    
    Load-EnvFile
    $port = $env:GATEWAY_HTTP_PORT
    if ([string]::IsNullOrWhiteSpace($port)) {
        $port = "8000"
    }
    
    Write-Host "Starting load tests with Locust..." -ForegroundColor Cyan
    $python = Get-VenvPython
    & $python -m locust -f services/gateway/tests/locustfile.py --host "http://localhost:$port"
}

function Clean-Files {
    Write-Host "Cleaning generated files..." -ForegroundColor Cyan
    
    # Remove __pycache__ directories
    Get-ChildItem -Path . -Recurse -Filter "__pycache__" -Directory | ForEach-Object {
        Remove-Item $_.FullName -Recurse -Force
        Write-Host "  Removed: $($_.FullName)" -ForegroundColor Gray
    }
    
    # Remove .pyc files
    Get-ChildItem -Path . -Recurse -Filter "*.pyc" -File | ForEach-Object {
        Remove-Item $_.FullName -Force
        Write-Host "  Removed: $($_.FullName)" -ForegroundColor Gray
    }
    
    # Remove .egg-info directories
    Get-ChildItem -Path . -Recurse -Filter "*.egg-info" -Directory | ForEach-Object {
        Remove-Item $_.FullName -Recurse -Force
        Write-Host "  Removed: $($_.FullName)" -ForegroundColor Gray
    }
    
    # Remove .pytest_cache directories
    Get-ChildItem -Path . -Recurse -Filter ".pytest_cache" -Directory | ForEach-Object {
        Remove-Item $_.FullName -Recurse -Force
        Write-Host "  Removed: $($_.FullName)" -ForegroundColor Gray
    }
    
    Write-Host "Cleanup complete" -ForegroundColor Green
}

function Clean-All {
    Write-Host "WARNING: This will remove all Docker volumes and data!" -ForegroundColor Yellow
    $confirmation = Read-Host "Are you sure? (yes/no)"
    
    if ($confirmation -eq "yes") {
        Clean-Files
        docker-compose down -v
        Write-Host "All data deleted!" -ForegroundColor Green
    } else {
        Write-Host "Operation cancelled" -ForegroundColor Yellow
    }
}

# ==================== Command Router ====================

switch ($Command.ToLower()) {
    "help"                { Show-Help }
    "setup"               { Setup }
    "proto"               { Compile-Proto }
    "up"                  { Start-Services }
    "down"                { Stop-Services }
    "logs"                { Show-Logs }
    "logs-auth"           { Show-AuthLogs }
    "logs-gateway"        { Show-GatewayLogs }
    "logs-ingestion"      { Show-IngestionLogs }
    "logs-worker"         { Show-WorkerLogs }
    "logs-analytics"      { Show-AnalyticsLogs }
    "logs-query"          { Show-QueryLogs }
    "restart"             { Restart-Services }
    "ps"                  { Show-Status }
    "build"               { Build-Images }
    "build-auth"          { Build-AuthImage }
    "build-gateway"       { Build-GatewayImage }
    "build-ingestion"     { Build-IngestionImage }
    "build-analytics"     { Build-AnalyticsImage }
    "build-query"         { Build-QueryImage }
    "db-migrate"          { Create-Migration }
    "db-upgrade"          { Apply-Migrations }
    "db-downgrade"        { Downgrade-Migration }
    "db-shell"            { Open-DatabaseShell }
    "logs-db-migrate"     { Create-LogsMigration }
    "logs-db-upgrade"     { Apply-LogsMigrations }
    "logs-db-downgrade"   { Downgrade-LogsMigration }
    "logs-db-shell"       { Open-LogsDatabase }
    "redis-cli"           { Open-RedisShell }
    "redis-flush"         { Flush-Redis }
    "test"                { Run-Tests }
    "test-auth"           { Run-AuthTests }
    "test-gateway"        { Run-GatewayTests }
    "test-ingestion"      { Run-IngestionTests }
    "test-analytics"      { Run-AnalyticsTests }
    "test-query"          { Run-QueryTests }
    "dev-auth"            { Run-DevAuth }
    "dev-gateway"         { Run-DevGateway }
    "dev-ingestion"       { Run-DevIngestion }
    "dev-worker"          { Run-DevWorker }
    "dev-analytics"       { Run-DevAnalytics }
    "dev-query"           { Run-DevQuery }
    "health"              { Check-Health }
    "load-test"           { Run-LoadTest }
    "clean"               { Clean-Files }
    "clean-all"           { Clean-All }
    default {
        Write-Host "Unknown command: $Command" -ForegroundColor Red
        Write-Host ""
        Show-Help
        exit 1
    }
}
