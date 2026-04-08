# ──────────────────────────────────────────────
# Khazanah Annual Review AI — One-Command Setup
# ──────────────────────────────────────────────
# Usage: .\setup.ps1
#   or:  powershell -ExecutionPolicy Bypass -File setup.ps1

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "+===========================================+" -ForegroundColor Cyan
Write-Host "|   Khazanah Annual Review AI - Setup       |" -ForegroundColor Cyan
Write-Host "+===========================================+" -ForegroundColor Cyan
Write-Host ""

# -- Check Docker ---------------------------------
$dockerCmd = Get-Command docker -ErrorAction SilentlyContinue
if (-not $dockerCmd) {
    Write-Host "Error: Docker is not installed." -ForegroundColor Red
    Write-Host "Install Docker Desktop: https://docs.docker.com/get-docker/"
    exit 1
}

try {
    docker info 2>&1 | Out-Null
} catch {
    Write-Host "Error: Docker daemon is not running." -ForegroundColor Red
    Write-Host "Please start Docker Desktop and try again."
    exit 1
}

# Also check via exit code
docker info 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Error: Docker daemon is not running." -ForegroundColor Red
    Write-Host "Please start Docker Desktop and try again."
    exit 1
}

Write-Host "[OK] Docker is running" -ForegroundColor Green

# -- Collect API Key ------------------------------
$SkipEnv = $false

if (Test-Path .env) {
    $envContent = Get-Content .env -Raw
    $match = [regex]::Match($envContent, "GEMINI_API_KEY=(.+)")
    if ($match.Success) {
        $existingKey = $match.Groups[1].Value.Trim()
        if ($existingKey -and $existingKey -ne "your-gemini-api-key-here") {
            Write-Host "[OK] Found existing .env with API key" -ForegroundColor Green
            $useExisting = Read-Host "Use existing key? (Y/n)"
            if ($useExisting -ne "n") {
                Write-Host "  Using existing .env"
                $SkipEnv = $true
            }
        }
    }
}

if (-not $SkipEnv) {
    Write-Host ""
    Write-Host "You need a Google Gemini API key (free)." -ForegroundColor Yellow
    Write-Host "Get one at: https://aistudio.google.com/apikey"
    Write-Host ""
    $apiKey = Read-Host "Enter your Gemini API key"

    if ([string]::IsNullOrWhiteSpace($apiKey)) {
        Write-Host "Error: API key cannot be empty." -ForegroundColor Red
        exit 1
    }

    # Generate .env from template
    $envTemplate = Get-Content .env.example -Raw
    $envContent = $envTemplate -replace "GEMINI_API_KEY=your-gemini-api-key-here", "GEMINI_API_KEY=$apiKey"
    Set-Content -Path .env -Value $envContent -NoNewline
    Write-Host "[OK] Created .env with your API key" -ForegroundColor Green
}

# -- Build & Start --------------------------------
Write-Host ""
Write-Host "Building and starting services (this may take a few minutes on first run)..."
Write-Host ""

docker compose up --build -d

if ($LASTEXITCODE -ne 0) {
    Write-Host "Error: docker compose failed. Check the output above." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "+===========================================+" -ForegroundColor Green
Write-Host "|   All services are running!               |" -ForegroundColor Green
Write-Host "|-------------------------------------------|" -ForegroundColor Green
Write-Host "|   Frontend:  http://localhost:3000        |" -ForegroundColor Green
Write-Host "|   API Docs:  http://localhost:8000/docs   |" -ForegroundColor Green
Write-Host "+===========================================+" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. Open http://localhost:3000"
Write-Host "  2. Upload PDFs on the Documents page"
Write-Host "  3. Click 'Run Ingestion' to process them"
Write-Host "  4. Go to Chat and start asking questions!"
Write-Host ""
Write-Host "To stop:  docker compose down"
Write-Host "To logs:  docker compose logs -f"
