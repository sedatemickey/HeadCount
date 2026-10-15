param([switch]$TestTools)
$ErrorActionPreference = 'Stop'
$Root = $PSScriptRoot
$Python = Join-Path $Root 'backend/.venv/Scripts/python.exe'

if (-not (Test-Path $Python)) {
    Write-Host '[1/4] Creating Python virtual environment...'
    & python -m venv (Join-Path $Root 'backend/.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.11+ is required.' }
}
Write-Host '[2/4] Installing pinned Python dependencies...'
$Target = Join-Path $Root 'backend'
if ($TestTools) { $Target = "$Target[test]" }
& $Python -m pip install -c (Join-Path $Root 'backend/requirements-lock.txt') -e $Target
if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }
Write-Host '[3/4] Installing frontend dependencies...'
& npm.cmd ci --prefix (Join-Path $Root 'frontend')
if ($LASTEXITCODE -ne 0) { throw 'npm ci failed. Node.js 22.12+ is required.' }
Write-Host '[4/4] Building local frontend assets...'
& npm.cmd run build --prefix (Join-Path $Root 'frontend')
if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
Write-Host 'Checking the selected local model (no model download)...'
& $Python -m app.model_cli doctor
if ($LASTEXITCODE -ne 0) { throw 'Model validation failed. See models/README.md for missing or invalid overrides.' }
Write-Host 'Setup complete. Run .\start.ps1, then open http://127.0.0.1:8000'
Write-Host 'The default medium model is bundled. Local replacements: models/local/ (see models/README.md).'
Write-Host 'Before redistribution, review the conflicting upstream license declarations in models/NOTICE.md.'
