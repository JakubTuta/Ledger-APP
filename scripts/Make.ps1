# Make.ps1 - PowerShell build script for Windows
# Usage: .\Make.ps1 <command>

param(
    [Parameter(Position=0)]
    [string]$Command = "help",

    [Parameter(Position=1, ValueFromRemainingArguments=$true)]
    [string[]]$Rest = @()
)

function Load-EnvFile {
    if (Test-Path .env) {
        Get-Content .env | ForEach-Object {
            if ($_ -match '^\s*([^#][^=]*)\s*=\s*(.*)$') {
                [Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim(), "Process")
            }
        }
    }
}

function Get-VenvPython {
    $venvPython = Join-Path $PWD "venv\Scripts\python.exe"
    if (Test-Path $venvPython) { return $venvPython }
    return "python"
}

function Get-VenvPip {
    $venvPip = Join-Path $PWD "venv\Scripts\pip.exe"
    if (Test-Path $venvPip) { return $venvPip }
    return "pip"
}

Load-EnvFile

# ==================== Commands ====================

function Show-Help {
    Write-Host "Available commands:" -ForegroundColor Cyan
    Write-Host "  setup        - Create venv, install deps, compile protos"
    Write-Host "  proto        - Compile protobuf files"
    Write-Host "  up           - Build and start all dev services"
    Write-Host "  down         - Stop all dev services"
    Write-Host "  test         - Run all tests"
    Write-Host "  test-auth    - Run auth service tests"
    Write-Host "  test-gateway - Run gateway service tests"
    Write-Host "  test-ingestion - Run ingestion service tests"
    Write-Host "  test-analytics - Run analytics workers tests"
    Write-Host "  test-query   - Run query service tests"
    Write-Host "  test-migrations - Run migration service tests"
    Write-Host "  test-e2e     - Run the end-to-end suite against a live stack (requires 'up' first)"
    Write-Host "  benchmark    - Measure max sustainable ingestion logs/s (steady-state --find-max, protobuf, exact DB verify)"
    Write-Host "  bench-up     - Start the stack unlimited (no CPU caps, SYS_PTRACE) - use for all A/B benchmark work"
    Write-Host "  bench-up-prod-parity - Start the stack capped exactly like docker-compose.prod.yaml"
    Write-Host ""
    Write-Host "Database (migration service, run against the local infra containers):" -ForegroundColor Yellow
    Write-Host "  db-status    - Show schema version, current revision and pending revisions per database"
    Write-Host "  db-upgrade   - Apply pending migrations   (--database auth|logs, --version N)"
    Write-Host "  db-downgrade - Roll back migrations       (--database auth|logs, --version N|--revision REV)"
    Write-Host "  db-migrate   - Create a revision file     (--database auth|logs -m ""message"")"
    Write-Host "  db-history   - Show revision history      (--database auth|logs)"
    Write-Host "  db-stamp     - Mark a revision as applied (--database auth|logs --revision REV)"
    Write-Host "  db-shell     - Open a psql shell          (auth|logs, default auth)"
    Write-Host ""
    Write-Host "Production:" -ForegroundColor Yellow
    Write-Host "  prod-deploy  - Build and push production images to registry"
    Write-Host "  prod-up      - Start production services"
    Write-Host "  prod-down    - Stop production services"
    Write-Host ""
    Write-Host "Usage: .\Make.ps1 <command>" -ForegroundColor Yellow
}

function Setup {
    if (-not (Test-Path .env)) {
        Copy-Item .env.example .env
        Write-Host "Created .env" -ForegroundColor Green
    }

    if (-not (Test-Path "venv")) {
        Write-Host "Creating virtual environment..." -ForegroundColor Cyan
        python -m venv venv
        if ($LASTEXITCODE -ne 0) { Write-Host "Failed to create venv" -ForegroundColor Red; exit 1 }
    }

    $pip = Get-VenvPip
    foreach ($service in @("auth", "gateway", "ingestion", "analytics", "query", "migrations")) {
        Write-Host "Installing $service dependencies..." -ForegroundColor Cyan
        Push-Location "services\$service"
        & $pip install -r requirements.txt
        Pop-Location
        if ($LASTEXITCODE -ne 0) { Write-Host "Failed to install $service dependencies" -ForegroundColor Red; exit 1 }
    }

    Compile-Proto
    Write-Host "Setup complete. Edit .env if needed, then run '.\Make.ps1 up'" -ForegroundColor Green
}

function Compile-Proto {
    Write-Host "Compiling protobuf files..." -ForegroundColor Cyan

    $protoDirs = @(
        "services\auth\auth_service\proto",
        "services\gateway\gateway_service\proto",
        "services\ingestion\ingestion_service\proto",
        "services\query\query_service\proto"
    )
    foreach ($dir in $protoDirs) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        $initFile = Join-Path $dir "__init__.py"
        if (-not (Test-Path $initFile)) { New-Item -ItemType File -Path $initFile -Force | Out-Null }
    }

    $python = Get-VenvPython
    $compilations = @(
        @{ Proto = "proto/auth.proto";      Out = "services/auth/auth_service/proto" },
        @{ Proto = "proto/auth.proto";      Out = "services/gateway/gateway_service/proto" },
        @{ Proto = "proto/ingestion.proto"; Out = "services/ingestion/ingestion_service/proto" },
        @{ Proto = "proto/ingestion.proto"; Out = "services/gateway/gateway_service/proto" },
        @{ Proto = "proto/query.proto";     Out = "services/query/query_service/proto" },
        @{ Proto = "proto/query.proto";     Out = "services/gateway/gateway_service/proto" }
    )
    foreach ($c in $compilations) {
        & $python -m grpc_tools.protoc -I=proto "--python_out=$($c.Out)" "--grpc_python_out=$($c.Out)" "--pyi_out=$($c.Out)" $c.Proto
        if ($LASTEXITCODE -ne 0) { Write-Host "Proto compilation failed: $($c.Proto) -> $($c.Out)" -ForegroundColor Red; exit 1 }
    }

    $fixImports = @(
        @{ File = "services\auth\auth_service\proto\auth_pb2_grpc.py";              Pattern = "import auth_pb2 as auth__pb2";           Replacement = "from . import auth_pb2 as auth__pb2" },
        @{ File = "services\gateway\gateway_service\proto\auth_pb2_grpc.py";        Pattern = "import auth_pb2 as auth__pb2";           Replacement = "from . import auth_pb2 as auth__pb2" },
        @{ File = "services\ingestion\ingestion_service\proto\ingestion_pb2_grpc.py"; Pattern = "import ingestion_pb2 as ingestion__pb2"; Replacement = "from . import ingestion_pb2 as ingestion__pb2" },
        @{ File = "services\gateway\gateway_service\proto\ingestion_pb2_grpc.py";   Pattern = "import ingestion_pb2 as ingestion__pb2"; Replacement = "from . import ingestion_pb2 as ingestion__pb2" },
        @{ File = "services\query\query_service\proto\query_pb2_grpc.py";           Pattern = "import query_pb2 as query__pb2";         Replacement = "from . import query_pb2 as query__pb2" },
        @{ File = "services\gateway\gateway_service\proto\query_pb2_grpc.py";       Pattern = "import query_pb2 as query__pb2";         Replacement = "from . import query_pb2 as query__pb2" }
    )
    foreach ($fix in $fixImports) {
        if (Test-Path $fix.File) {
            $content = Get-Content $fix.File -Raw
            $content = $content -replace [regex]::Escape($fix.Pattern), $fix.Replacement
            Set-Content $fix.File -Value $content -NoNewline
        }
    }

    Write-Host "Protobuf compiled" -ForegroundColor Green
}

function Start-Services {
    docker-compose down --rmi local
    if ($LASTEXITCODE -ne 0) { Write-Host "Failed to remove old containers/images" -ForegroundColor Red; exit 1 }
    docker-compose up -d --build
    if ($LASTEXITCODE -ne 0) { Write-Host "Failed to start services" -ForegroundColor Red; exit 1 }
    Write-Host "Services started" -ForegroundColor Green
}

function Stop-Services {
    docker-compose down
    if ($LASTEXITCODE -ne 0) { Write-Host "Failed to stop services" -ForegroundColor Red; exit 1 }
    Write-Host "Services stopped" -ForegroundColor Green
}

function Start-BenchUnlimited {
    docker-compose -f docker-compose.yaml -f docker-compose.bench-unlimited.yaml up -d --build
    if ($LASTEXITCODE -ne 0) { Write-Host "Failed to start bench-unlimited stack" -ForegroundColor Red; exit 1 }
    Write-Host "bench-unlimited stack started (no CPU/memory caps, SYS_PTRACE for py-spy)" -ForegroundColor Green
}

function Start-BenchProdParity {
    docker-compose --compatibility -f docker-compose.yaml -f docker-compose.bench-prod-parity.yaml up -d --build
    if ($LASTEXITCODE -ne 0) { Write-Host "Failed to start bench-prod-parity stack" -ForegroundColor Red; exit 1 }
    Write-Host "bench-prod-parity stack started - verify limits landed with:" -ForegroundColor Green
    Write-Host "  docker inspect ledger-ingestion-worker --format '{{.HostConfig.NanoCpus}} {{.HostConfig.Memory}}'" -ForegroundColor Yellow
}

function Run-Tests {
    param([string]$Service = "")

    if (-not (Test-Path "venv")) {
        Write-Host "Virtual environment not found. Run '.\Make.ps1 setup' first." -ForegroundColor Red
        exit 1
    }

    $python = Get-VenvPython
    $services = if ($Service) { @($Service) } else { @("auth", "gateway", "ingestion", "analytics", "query", "migrations") }
    $failed = @()

    foreach ($svc in $services) {
        Write-Host "Testing $svc..." -ForegroundColor Cyan
        Push-Location "services\$svc"
        & $python -m pytest tests/ -v
        if ($LASTEXITCODE -ne 0) { $failed += $svc }
        Pop-Location
    }

    if ($failed.Count -gt 0) {
        Write-Host "Failed: $($failed -join ', ')" -ForegroundColor Red
        exit 1
    }
    Write-Host "All tests passed" -ForegroundColor Green
}

function Run-E2ETests {
    if (-not (Test-Path "venv")) {
        Write-Host "Virtual environment not found. Run '.\Make.ps1 setup' first." -ForegroundColor Red
        exit 1
    }

    $baseUrl = if ($env:E2E_BASE_URL) { $env:E2E_BASE_URL } else { "http://localhost:8020" }
    Write-Host "Checking stack health at $baseUrl/health..." -ForegroundColor Cyan
    try {
        $response = Invoke-WebRequest -Uri "$baseUrl/health" -TimeoutSec 5 -UseBasicParsing
        if ($response.StatusCode -ne 200) { throw "unhealthy" }
    } catch {
        Write-Host "Stack is not reachable/healthy at $baseUrl. Run '.\Make.ps1 up' first." -ForegroundColor Red
        exit 1
    }

    $python = Get-VenvPython
    Write-Host "Running E2E suite (local-only, no CI job) against $baseUrl..." -ForegroundColor Cyan
    Push-Location "tests\e2e"
    & $python -m pytest . -v
    $exitCode = $LASTEXITCODE
    Pop-Location

    if ($exitCode -ne 0) {
        Write-Host "E2E tests failed" -ForegroundColor Red
        exit 1
    }
    Write-Host "All E2E tests passed" -ForegroundColor Green
}

# ==================== Database ====================

function Invoke-Migrations {
    param([string[]]$Arguments)

    if (-not (Test-Path "venv")) {
        Write-Host "Virtual environment not found. Run '.\Make.ps1 setup' first." -ForegroundColor Red
        exit 1
    }

    # .env carries the compose hostnames, which do not resolve from the host, and
    # the logs DB is published on 5433 rather than its container port.
    $env:ENV_FILE_PATH = (Join-Path $PWD ".env")
    $env:AUTH_DB_HOST = "localhost"
    $env:AUTH_DB_PORT = "5432"
    $env:LOGS_DB_HOST = "localhost"
    $env:LOGS_DB_PORT = "5433"

    $python = Get-VenvPython
    Push-Location "services\migrations"
    & $python -m migration_service @Arguments
    $exitCode = $LASTEXITCODE
    Pop-Location

    if ($exitCode -ne 0) { exit 1 }
}

function Open-DbShell {
    param([string]$Database = "auth")

    switch ($Database.ToLower()) {
        "auth" { $container = "ledger-postgres";      $user = $env:AUTH_DB_USER; $name = $env:AUTH_DB_NAME }
        "logs" { $container = "ledger-postgres-logs"; $user = $env:LOGS_DB_USER; $name = $env:LOGS_DB_NAME }
        default {
            Write-Host "Unknown database '$Database'. Use 'auth' or 'logs'." -ForegroundColor Red
            exit 1
        }
    }

    docker exec -it $container psql -U $user -d $name
    if ($LASTEXITCODE -ne 0) { exit 1 }
}

function Run-Benchmark {
    if (-not (Test-Path "venv")) {
        Write-Host "Virtual environment not found. Run '.\Make.ps1 setup' first." -ForegroundColor Red
        exit 1
    }
    $python = Get-VenvPython
    Write-Host "Starting ingestion benchmark (steady-state --find-max, protobuf, exact DB verify)..." -ForegroundColor Cyan
    & $python "scripts\benchmark\__main__.py"
    if ($LASTEXITCODE -ne 0) { Write-Host "Benchmark failed" -ForegroundColor Red; exit 1 }
}

# ==================== Production ====================

$PROD_REGISTRY = "container-registry.jtuta.cloud/ledger"
$PROD_TAG = "latest"
$PROD_SERVICES = @("auth", "gateway", "ingestion", "analytics", "query", "migrations")

function Assert-Docker {
    try { docker version | Out-Null } catch {
        Write-Host "Docker is not running or not installed" -ForegroundColor Red; exit 1
    }
}

function Assert-Registry {
    $configFile = Join-Path $env:USERPROFILE ".docker\config.json"
    $authenticated = $false
    if (Test-Path $configFile) {
        try {
            $config = Get-Content $configFile -Raw | ConvertFrom-Json
            $authenticated = $null -ne $config.auths."container-registry.jtuta.cloud"
        } catch {}
    }
    if (-not $authenticated) {
        Write-Host "Registry authentication required. Logging in..." -ForegroundColor Yellow
        docker login container-registry.jtuta.cloud
        if ($LASTEXITCODE -ne 0) { Write-Host "Failed to login to registry" -ForegroundColor Red; exit 1 }
    }
}

function Build-ProdImage {
    param([string]$ServiceName)
    $image = "$PROD_REGISTRY/${ServiceName}:${PROD_TAG}"
    Write-Host "Building $ServiceName -> $image" -ForegroundColor Cyan
    docker build --file "services/$ServiceName/Dockerfile" --tag $image --platform linux/amd64 "services/$ServiceName"
    if ($LASTEXITCODE -ne 0) { Write-Host "[ERROR] Failed to build $ServiceName" -ForegroundColor Red; return $false }
    Write-Host "[SUCCESS] $ServiceName built" -ForegroundColor Green
    return $true
}

function Push-ProdImage {
    param([string]$ServiceName)
    $image = "$PROD_REGISTRY/${ServiceName}:${PROD_TAG}"
    Write-Host "Pushing $image" -ForegroundColor Cyan
    docker push $image
    if ($LASTEXITCODE -ne 0) { Write-Host "[ERROR] Failed to push $ServiceName" -ForegroundColor Red; return $false }
    Write-Host "[SUCCESS] $ServiceName pushed" -ForegroundColor Green
    return $true
}

function Run-ProdDeploy {
    Assert-Docker; Assert-Registry
    $failed = @()
    foreach ($svc in $PROD_SERVICES) {
        if ((Build-ProdImage -ServiceName $svc) -and (Push-ProdImage -ServiceName $svc)) { continue }
        $failed += $svc
    }
    if ($failed.Count -gt 0) { Write-Host "Failed: $($failed -join ', ')" -ForegroundColor Red; exit 1 }
    Write-Host "All production images deployed" -ForegroundColor Green
}

function Start-ProdServices {
    docker-compose -f docker-compose.prod.yaml up -d
    if ($LASTEXITCODE -ne 0) { Write-Host "Failed to start production services" -ForegroundColor Red; exit 1 }
    Write-Host "Production services started" -ForegroundColor Green
}

function Stop-ProdServices {
    docker-compose -f docker-compose.prod.yaml down
    if ($LASTEXITCODE -ne 0) { Write-Host "Failed to stop production services" -ForegroundColor Red; exit 1 }
    Write-Host "Production services stopped" -ForegroundColor Green
}

# ==================== Router ====================

switch ($Command.ToLower()) {
    "help"             { Show-Help }
    "setup"            { Setup }
    "proto"            { Compile-Proto }
    "up"               { Start-Services }
    "down"             { Stop-Services }
    "bench-up"              { Start-BenchUnlimited }
    "bench-up-prod-parity"  { Start-BenchProdParity }
    "test"             { Run-Tests }
    "test-auth"        { Run-Tests -Service "auth" }
    "test-gateway"     { Run-Tests -Service "gateway" }
    "test-ingestion"   { Run-Tests -Service "ingestion" }
    "test-analytics"   { Run-Tests -Service "analytics" }
    "test-query"       { Run-Tests -Service "query" }
    "test-migrations"  { Run-Tests -Service "migrations" }
    "test-e2e"         { Run-E2ETests }
    "benchmark"        { Run-Benchmark }
    "db-status"        { Invoke-Migrations (@("status")    + $Rest) }
    "db-upgrade"       { Invoke-Migrations (@("upgrade")   + $Rest) }
    "db-downgrade"     { Invoke-Migrations (@("downgrade") + $Rest) }
    "db-migrate"       { Invoke-Migrations (@("revision")  + $Rest) }
    "db-history"       { Invoke-Migrations (@("history")   + $Rest) }
    "db-stamp"         { Invoke-Migrations (@("stamp")     + $Rest) }
    "db-shell"         { if ($Rest.Count -gt 0) { Open-DbShell -Database $Rest[0] } else { Open-DbShell } }
    "prod-deploy"      { Run-ProdDeploy }
    "prod-up"          { Start-ProdServices }
    "prod-down"        { Stop-ProdServices }
    default            { Write-Host "Unknown command: $Command. Run '.\Make.ps1 help'" -ForegroundColor Red; exit 1 }
}
