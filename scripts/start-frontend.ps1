$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$portableNode = Join-Path $projectRoot '.tools\node'
if (Test-Path -LiteralPath (Join-Path $portableNode 'node.exe')) {
    $env:PATH = "$portableNode;$env:PATH"
}
$npmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
if (-not $npmCommand) { throw 'Falta Node.js con npm. Consulta el README.' }
Push-Location (Join-Path $projectRoot 'frontend')
try {
    & $npmCommand.Source run dev
    if ($LASTEXITCODE -ne 0) { throw 'El frontend terminó con un error.' }
} finally {
    Pop-Location
}
