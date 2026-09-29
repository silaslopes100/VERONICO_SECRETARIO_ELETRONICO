# =============================================================================
# Shortcut â€” launcher para Windows
# 1) instala dependÃªncias (venv, requirements, Chromium, npm)
# 2) encerra instÃ¢ncias antigas DO PROJETO (evita porta duplicada)
# 3) sobe backend (8000) + frontend (5173) e valida o health check
# O Chromium controlado (QR Code do WhatsApp) Ã© aberto pelo prÃ³prio backend.
# =============================================================================
$ErrorActionPreference = "Stop"

$Root      = Split-Path -Parent $PSScriptRoot
$Launcher  = $PSScriptRoot
$Backend   = Join-Path $Root "backend"
$Frontend  = Join-Path $Root "frontend"
$VenvPy    = Join-Path $Backend ".venv\Scripts\python.exe"
$BackendUrl = "http://localhost:8000/api/health"
$FrontendUrl = "http://localhost:5173"

Write-Host "=== Shortcut ===" -ForegroundColor Cyan

# ---------------------------------------------------------------- dependencias
$sysPython = if (Get-Command python -ErrorAction SilentlyContinue) { "python" }
             elseif (Get-Command py -ErrorAction SilentlyContinue) { "py -3" }
             else { $null }
if (-not $sysPython) {
    Write-Host "Python 3.11+ nao encontrado. Instale em https://python.org" -ForegroundColor Red
    exit 1
}
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Write-Host "Node.js 18+ nao encontrado. Instale em https://nodejs.org" -ForegroundColor Red
    exit 1
}

Write-Host "[1/6] Instalando dependencias (pode demorar na primeira vez)..." -ForegroundColor Yellow
& $sysPython (Join-Path $Launcher "install_dependencies.py")
if ($LASTEXITCODE -ne 0) {
    Write-Host "Falha na instalacao das dependencias." -ForegroundColor Red
    exit 1
}
if (-not (Test-Path $VenvPy)) {
    Write-Host "Virtualenv nao foi criado em $VenvPy" -ForegroundColor Red
    exit 1
}

# --------------------------------------------- instâncias antigas do projeto
Write-Host "[2/6] Encerrando instancias antigas do Shortcut (se houver)..." -ForegroundColor Yellow
$rootPattern = [regex]::Escape($Root)
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object {
        $_.CommandLine -and
        ($_.CommandLine -match "$rootPattern.*run_backend\.py" -or
         $_.CommandLine -match "$rootPattern[\\/]+frontend.*vite") -and
        $_.ProcessId -ne $PID
    } |
    ForEach-Object {
        Write-Host "   - matando PID $($_.ProcessId)" -ForegroundColor DarkGray
        & taskkill /PID $_.ProcessId /T /F 2>$null | Out-Null
    }
Start-Sleep -Seconds 2

$occupied = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($occupied) {
    $owner = Get-Process -Id $occupied[0].OwningProcess -ErrorAction SilentlyContinue
    Write-Host "   ! A porta 8000 ainda esta ocupada por outro programa ($($owner.ProcessName))." -ForegroundColor Red
    Write-Host "     Encerre esse programa ou altere BACKEND_PORT em .env" -ForegroundColor Red
    exit 1
}

# ------------------------------------------------------------- .env de exemplo
$envExample = Join-Path $Root ".env.example"
$envFile    = Join-Path $Root ".env"
if (-not (Test-Path $envFile) -and (Test-Path $envExample)) {
    Copy-Item $envExample $envFile
    Write-Host "Criado .env a partir de .env.example (edite conforme necessario)." -ForegroundColor DarkYellow
}
if (-not $env:SHORTCUT_MASTER_KEY) {
    Write-Host "Aviso: SHORTCUT_MASTER_KEY nao definida (obrigatoria para .env.enc). Consulte o README." -ForegroundColor DarkYellow
}

# --------------------------------------------------------------------- servers
Write-Host "[3/6] Subindo backend (FastAPI + Playwright)..." -ForegroundColor Yellow
$backendProc = Start-Process -FilePath $VenvPy `
    -ArgumentList "run_backend.py" `
    -WorkingDirectory $Backend `
    -PassThru -WindowStyle Normal

Write-Host "[4/6] Aguardando o health check do backend..." -ForegroundColor Yellow
$backendOk = $false
for ($i = 0; $i -lt 15; $i++) {
    Start-Sleep -Seconds 2
    if ($backendProc.HasExited) { break }
    try {
        $health = Invoke-RestMethod $BackendUrl -TimeoutSec 2
        if ($health.service -eq "shortcut-backend") { $backendOk = $true; break }
    } catch { }
}
if (-not $backendOk) {
    Write-Host "Backend nao subiu (porta 8000 nao respondeu /api/health)." -ForegroundColor Red
    if (-not $backendProc.HasExited) { & taskkill /PID $backendProc.Id /T /F 2>$null | Out-Null }
    exit 1
}
Write-Host "   backend OK em $BackendUrl" -ForegroundColor Green

Write-Host "[5/6] Subindo frontend (Vite)..." -ForegroundColor Yellow
$frontendProc = Start-Process -FilePath "cmd.exe" `
    -ArgumentList "/c", "npm run dev" `
    -WorkingDirectory $Frontend `
    -PassThru -WindowStyle Normal

$frontendOk = $false
for ($i = 0; $i -lt 15; $i++) {
    Start-Sleep -Seconds 2
    if ($frontendProc.HasExited) { break }
    try {
        $null = Invoke-WebRequest $FrontendUrl -TimeoutSec 2 -UseBasicParsing
        $frontendOk = $true; break
    } catch { }
}
if (-not $frontendOk) {
    Write-Host "Frontend nao subiu em $FrontendUrl." -ForegroundColor Red
    & taskkill /PID $frontendProc.Id /T /F 2>$null | Out-Null
    & taskkill /PID $backendProc.Id /T /F 2>$null | Out-Null
    exit 1
}

Write-Host "[6/6] Tudo no ar!" -ForegroundColor Green
Write-Host ""
Write-Host "Shortcut no ar!" -ForegroundColor Green
Write-Host "  Frontend : http://localhost:5173"
Write-Host "  Backend  : http://localhost:8000 (docs em /docs)"
Write-Host "  WhatsApp : escaneie o QR Code na janela Chromium aberta pelo backend."
Write-Host "  Encerrar : pressione Ctrl+C nesta janela." -ForegroundColor DarkGray
Write-Host ""

# ------------------------------------------------------------------- shutdown
try {
    while ($true) {
        if ($backendProc.HasExited)  { Write-Host "Backend encerrou inesperadamente." -ForegroundColor Red; break }
        if ($frontendProc.HasExited) { Write-Host "Frontend encerrou inesperadamente." -ForegroundColor Red; break }
        Start-Sleep -Seconds 2
    }
}
finally {
    Write-Host "Encerrando processos do Shortcut..." -ForegroundColor Yellow
    foreach ($proc in @($frontendProc, $backendProc)) {
        if ($proc -and -not $proc.HasExited) {
            & taskkill /PID $proc.Id /T /F 2>$null | Out-Null
        }
    }
    Write-Host "Ate logo!" -ForegroundColor Cyan
}

