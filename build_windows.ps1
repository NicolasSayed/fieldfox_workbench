param(
    [ValidateSet('onedir','onefile','both')][string]$Mode = 'both',
    [switch]$SkipInstall
)
$ErrorActionPreference = 'Stop'
$projectPath = $PSScriptRoot
Push-Location -LiteralPath $projectPath
try {
    $pythonPath = Join-Path $projectPath '.venv-build\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $pythonPath)) {
        & py -3.11 -m venv .venv-build
        if ($LASTEXITCODE -ne 0) { throw 'Creating the Python 3.11 build environment failed.' }
    }
    if (-not $SkipInstall) {
        & $pythonPath -m pip install --disable-pip-version-check -r requirements-build.txt
        if ($LASTEXITCODE -ne 0) { throw 'Installing build dependencies failed.' }
    }
    & $pythonPath scripts/build_exe.py --mode $Mode --max-mib 300
    if ($LASTEXITCODE -ne 0) { throw 'Executable build or frozen self-test failed; see build logs.' }
} finally { Pop-Location }
