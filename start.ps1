$ErrorActionPreference = 'Stop'
$Root = $PSScriptRoot
$Python = Join-Path $Root 'backend/.venv/Scripts/python.exe'
if (-not (Test-Path $Python) -or -not (Test-Path (Join-Path $Root 'frontend/dist/index.html'))) {
    throw 'Run .\setup.ps1 first.'
}
Write-Host 'HeadCount: http://127.0.0.1:8000'
Write-Host 'Data is stored locally. Press Ctrl+C to stop. Do not run multiple backend processes.'
& $Python -m uvicorn app.main:create_app --factory --app-dir (Join-Path $Root 'backend') --host 127.0.0.1 --port 8000
exit $LASTEXITCODE
