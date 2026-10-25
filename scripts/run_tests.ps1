param(
    [switch]$WithPostgres
)

$ErrorActionPreference = "Stop"

# Prefer the virtual environment currently activated in PowerShell. This allows
# developers to use a versioned environment name such as .venv313 as well as .venv.
if ($env:VIRTUAL_ENV) {
    $python = Join-Path $env:VIRTUAL_ENV "Scripts\\python.exe"
}
elseif (Test-Path ".venv\\Scripts\\python.exe") {
    $python = ".venv\\Scripts\\python.exe"
}
else {
    throw "Activate a virtual environment first, then run this script."
}

if (-not (Test-Path $python)) {
    throw "Python was not found in the active virtual environment: $python"
}

if ($WithPostgres) {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw "Docker Desktop is required for -WithPostgres. Start/install Docker Desktop, then run this command again."
    }
    docker compose up -d postgres
    $ready = $false
    for ($attempt = 1; $attempt -le 20; $attempt++) {
        docker compose exec -T postgres pg_isready -U krishi -d krishi_awaaz | Out-Null
        if ($LASTEXITCODE -eq 0) {
            $ready = $true
            break
        }
        Start-Sleep -Seconds 2
    }
    if (-not $ready) {
        throw "PostgreSQL did not become ready within 40 seconds."
    }
    $env:DATABASE_URL = "postgresql+psycopg://krishi:krishi@localhost:5433/krishi_awaaz"
    $env:RUN_POSTGRES_TESTS = "1"
}

& $python -m ruff check .
& $python -m ruff format --check .
& $python -m pytest -q
