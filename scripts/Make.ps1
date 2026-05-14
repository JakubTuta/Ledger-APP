# Make.ps1 - PowerShell build script for Windows
# Usage: .\Make.ps1 <command>

param(
    [Parameter(Position=0)]
    [string]$Command = "help"
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
    Write-Host "  up           - Start all dev services"
    Write-Host "  down         - Stop all dev services"
    Write-Host "  build        - Build dev Docker images"
    Write-Host "  redeploy     - Stop, rebuild and start dev services"
    Write-Host "  test         - Run all tests"
    Write-Host "  test-auth    - Run auth service tests"
    Write-Host "  test-gateway - Run gateway service tests"
    Write-Host "  test-ingestion - Run ingestion service tests"
    Write-Host "  test-analytics - Run analytics workers tests"
    Write-Host "  test-query   - Run query service tests"
    Write-Host ""
    Write-Host "Production:" -ForegroundColor Yellow
    Write-Host "  prod-build   - Build production images for registry"
    Write-Host "  prod-push    - Push production images to registry"
    Write-Host "  prod-deploy  - Build and push production images"
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
    foreach ($service in @("auth", "gateway", "ingestion", "analytics", "query")) {
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
    docker-compose up -d
    if ($LASTEXITCODE -ne 0) { Write-Host "Failed to start services" -ForegroundColor Red; exit 1 }
    Write-Host "Services started" -ForegroundColor Green
}

function Stop-Services {
    docker-compose down
    if ($LASTEXITCODE -ne 0) { Write-Host "Failed to stop services" -ForegroundColor Red; exit 1 }
    Write-Host "Services stopped" -ForegroundColor Green
}

function Build-Images {
    docker-compose build
    if ($LASTEXITCODE -ne 0) { Write-Host "Build failed" -ForegroundColor Red; exit 1 }
    Write-Host "Build complete" -ForegroundColor Green
}

function Redeploy-Services {
    Stop-Services
    Build-Images
    Start-Services
}

function Run-Tests {
    param([string]$Service = "")

    if (-not (Test-Path "venv")) {
        Write-Host "Virtual environment not found. Run '.\Make.ps1 setup' first." -ForegroundColor Red
        exit 1
    }

    $python = Get-VenvPython
    $services = if ($Service) { @($Service) } else { @("auth", "gateway", "ingestion", "analytics", "query") }
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

# ==================== Production ====================

$PROD_REGISTRY = "container-registry.jtuta.cloud/ledger"
$PROD_TAG = "latest"
$PROD_SERVICES = @("auth", "gateway", "ingestion", "analytics", "query")

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

function Run-ProdBuild {
    Assert-Docker
    $failed = @()
    foreach ($svc in $PROD_SERVICES) {
        if (-not (Build-ProdImage -ServiceName $svc)) { $failed += $svc }
    }
    if ($failed.Count -gt 0) { Write-Host "Failed: $($failed -join ', ')" -ForegroundColor Red; exit 1 }
    Write-Host "All production images built" -ForegroundColor Green
}

function Run-ProdPush {
    Assert-Docker; Assert-Registry
    $failed = @()
    foreach ($svc in $PROD_SERVICES) {
        if (-not (Push-ProdImage -ServiceName $svc)) { $failed += $svc }
    }
    if ($failed.Count -gt 0) { Write-Host "Failed: $($failed -join ', ')" -ForegroundColor Red; exit 1 }
    Write-Host "All production images pushed" -ForegroundColor Green
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
    "build"            { Build-Images }
    "redeploy"         { Redeploy-Services }
    "test"             { Run-Tests }
    "test-auth"        { Run-Tests -Service "auth" }
    "test-gateway"     { Run-Tests -Service "gateway" }
    "test-ingestion"   { Run-Tests -Service "ingestion" }
    "test-analytics"   { Run-Tests -Service "analytics" }
    "test-query"       { Run-Tests -Service "query" }
    "prod-build"       { Run-ProdBuild }
    "prod-push"        { Run-ProdPush }
    "prod-deploy"      { Run-ProdDeploy }
    "prod-up"          { Start-ProdServices }
    "prod-down"        { Stop-ProdServices }
    default            { Write-Host "Unknown command: $Command. Run '.\Make.ps1 help'" -ForegroundColor Red; exit 1 }
}
