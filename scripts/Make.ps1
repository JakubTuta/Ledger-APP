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
    Write-Host "  help        - Show this help message"
    Write-Host "  setup       - Initial setup (copy .env, install deps, compile protos)"
    Write-Host "  proto       - Compile protobuf files"
    Write-Host "  up          - Start all services"
    Write-Host "  down        - Stop all services"
    Write-Host "  logs        - View logs"
    Write-Host "  restart     - Restart all services"
    Write-Host "  ps          - Show service status"
    Write-Host "  build       - Build Docker images"
    Write-Host "  db-migrate  - Generate new migration"
    Write-Host "  db-upgrade  - Apply migrations"
    Write-Host "  db-shell    - Open database shell"
    Write-Host "  redis-cli   - Open Redis CLI"
    Write-Host "  test        - Run tests"
    Write-Host "  dev         - Run auth service locally"
    Write-Host "  clean       - Clean generated files"
    Write-Host "  clean-all   - Clean everything including Docker volumes"
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
        Write-Host "Failed to install dependencies" -ForegroundColor Red
        exit 1
    }
    
    # Compile protobuf files
    Compile-Proto
    
    Write-Host "Setup complete! Edit .env if needed, then run '.\Make.ps1 up'" -ForegroundColor Green
}

function Compile-Proto {
    Write-Host "Compiling protobuf files..." -ForegroundColor Cyan
    
    # Create proto directory if it doesn't exist
    $protoDir = "services\auth\auth_service\proto"
    if (-not (Test-Path $protoDir)) {
        New-Item -ItemType Directory -Path $protoDir -Force | Out-Null
    }
    
    # Create __init__.py if it doesn't exist
    $initFile = Join-Path $protoDir "__init__.py"
    if (-not (Test-Path $initFile)) {
        New-Item -ItemType File -Path $initFile -Force | Out-Null
        Write-Host "Created $initFile" -ForegroundColor Gray
    }
    
    # Use venv python if available
    $python = Get-VenvPython
    
    & $python -m grpc_tools.protoc `
        -I=proto `
        --python_out=services/auth/auth_service/proto `
        --grpc_python_out=services/auth/auth_service/proto `
        --pyi_out=services/auth/auth_service/proto `
        proto/auth.proto
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Protobuf compiled" -ForegroundColor Green
        
        # Fix imports in generated gRPC file to use relative imports
        $grpcFile = "services\auth\auth_service\proto\auth_pb2_grpc.py"
        if (Test-Path $grpcFile) {
            $content = Get-Content $grpcFile -Raw
            $content = $content -replace "import auth_pb2 as auth__pb2", "from . import auth_pb2 as auth__pb2"
            Set-Content $grpcFile -Value $content -NoNewline
            Write-Host "Fixed imports in auth_pb2_grpc.py" -ForegroundColor Green
        }
    } else {
        Write-Host "Protobuf compilation failed" -ForegroundColor Red
        exit 1
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
    docker-compose logs -f auth-service
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

function Open-DatabaseShell {
    Load-EnvFile
    $dbUser = $env:AUTH_DB_USER
    $dbName = $env:AUTH_DB_NAME
    
    Write-Host "Opening database shell..." -ForegroundColor Cyan
    docker-compose exec postgres psql -U $dbUser -d $dbName
}

function Open-RedisShell {
    Write-Host "Opening Redis CLI..." -ForegroundColor Cyan
    docker-compose exec redis redis-cli
}

function Run-Tests {
    if (-not (Test-Path "venv")) {
        Write-Host "Virtual environment not found. Run '.\Make.ps1 setup' first." -ForegroundColor Red
        exit 1
    }
    
    Write-Host "Running tests..." -ForegroundColor Cyan
    $python = Get-VenvPython
    Push-Location services\auth
    & $python -m pytest tests/ -v
    Pop-Location
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Tests passed" -ForegroundColor Green
    } else {
        Write-Host "Tests failed" -ForegroundColor Red
        exit 1
    }
}

function Run-Dev {
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
    "help"       { Show-Help }
    "setup"      { Setup }
    "proto"      { Compile-Proto }
    "up"         { Start-Services }
    "down"       { Stop-Services }
    "logs"       { Show-Logs }
    "restart"    { Restart-Services }
    "ps"         { Show-Status }
    "build"      { Build-Images }
    "db-migrate" { Create-Migration }
    "db-upgrade" { Apply-Migrations }
    "db-shell"   { Open-DatabaseShell }
    "redis-cli"  { Open-RedisShell }
    "test"       { Run-Tests }
    "dev"        { Run-Dev }
    "clean"      { Clean-Files }
    "clean-all"  { Clean-All }
    default {
        Write-Host "Unknown command: $Command" -ForegroundColor Red
        Write-Host ""
        Show-Help
        exit 1
    }
}
