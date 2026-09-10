$ErrorActionPreference = "Stop"

Write-Host "========================================="
Write-Host " CORTEX - Operation CyberHawk 2.0 demo"
Write-Host "========================================="
Write-Host ""

$baseDir = $PSScriptRoot
$backendDir = Join-Path $baseDir "backend"
$frontendDir = Join-Path $baseDir "frontend-next"
$python = Join-Path $backendDir ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    throw "No virtualenv at $python. Create one with: python -m venv backend\.venv"
}

# The demo runs against its own SQLite file on its own ports, so it never touches whatever
# backend\.env points at. A real environment variable wins over the .env file in pydantic-settings,
# which is what keeps that guarantee.
$env:CNA_DATABASE_URL = "sqlite:///./demo.db"
$env:CNA_DEFAULT_CORPUS = "none"

Write-Host "--> Loading the demo sheet from demo-case-data\*.csv ..."
Push-Location $backendDir
& $python -m app.ingestion.load_demo_case
if ($LASTEXITCODE -ne 0) { Pop-Location; throw "Demo load failed." }
Pop-Location

Write-Host "--> Starting the API on port 8001 ..."
Start-Process -FilePath $python -ArgumentList "-m", "uvicorn", "app.main:app", "--port", "8001" `
    -WorkingDirectory $backendDir -WindowStyle Normal

Write-Host "--> Starting the console on port 3001 ..."
$env:NEXT_PUBLIC_API_URL = "http://localhost:8001"
Start-Process -FilePath "npm.cmd" -ArgumentList "run", "dev:demo" `
    -WorkingDirectory $frontendDir -WindowStyle Normal

Write-Host ""
Write-Host "========================================="
Write-Host " Console:  http://localhost:3001"
Write-Host " API:      http://localhost:8001/docs"
Write-Host " Sign in:  analyst / analyst@123"
Write-Host " (Each service has its own window for logs.)"
Write-Host "========================================="
