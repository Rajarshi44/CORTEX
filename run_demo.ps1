$ErrorActionPreference = "Stop"

Write-Host "========================================="
Write-Host " Starting SUTRA Demo Instance (Isolated)"
Write-Host "========================================="
Write-Host ""

# Paths
$baseDir = $PSScriptRoot
$backendDir = Join-Path $baseDir "backend"
$frontendDir = Join-Path $baseDir "frontend-next"

# 1. Load Data
Write-Host "--> Loading demo database..."
Set-Location $backendDir
$env:DOTENV_PATH = ".env.demo"
.\venv\Scripts\python -m app.ingestion.load_demo_case

# 2. Start Backend
Write-Host "--> Starting backend on port 8001..."
Start-Process -FilePath ".\venv\Scripts\python" -ArgumentList "-m uvicorn app.main:app --port 8001" -WindowStyle Normal

# 3. Start Frontend
Write-Host "--> Starting frontend on port 3001..."
Set-Location $frontendDir
$env:NEXT_PUBLIC_API_URL = "http://localhost:8001"
Start-Process -FilePath "npm" -ArgumentList "run dev -- -p 3001" -WindowStyle Normal

Write-Host ""
Write-Host "========================================="
Write-Host " Demo instance launched!"
Write-Host " Frontend: http://localhost:3001"
Write-Host " Backend:  http://localhost:8001"
Write-Host " (Separate windows have opened for logs)"
Write-Host "========================================="
