param([int]$Port = 8000, [switch]$Reload)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$backendRoot = Join-Path $projectRoot 'backend'
$pythonExe = Join-Path $backendRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw 'Falta backend/.venv. Instala las dependencias siguiendo el README.'
}
Push-Location $backendRoot
try {
    & $pythonExe -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw 'No se pudieron aplicar las migraciones.' }
    $serverArguments = @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', "$Port", '--workers', '1')
    if ($Reload) { $serverArguments += '--reload' }
    & $pythonExe @serverArguments
    if ($LASTEXITCODE -ne 0) { throw 'El backend terminó con un error.' }
} finally {
    Pop-Location
}
