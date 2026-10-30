param(
    [ValidateSet('onedir','onefile','both')][string]$Mode = 'onefile',
    [switch]$SkipInstall
)
$ErrorActionPreference = 'Stop'
$projectPath = $PSScriptRoot
Push-Location -LiteralPath $projectPath
try {
    $pythonPath = Join-Path $projectPath '.venv-build\Scripts\python.exe'
    if (Test-Path -LiteralPath $pythonPath) {
        & $pythonPath -c 'import sys,struct; sys.exit(0 if sys.version_info[:2] == (3,11) and struct.calcsize(chr(80)) == 8 else 1)'
        if ($LASTEXITCODE -ne 0) {
            Write-Host 'The existing build environment uses a different Python; preserving it and using .venv-build-py311.'
            $pythonPath = Join-Path $projectPath '.venv-build-py311\Scripts\python.exe'
        }
    }
    if (-not (Test-Path -LiteralPath $pythonPath)) {
        $environmentPath = Split-Path -Parent (Split-Path -Parent $pythonPath)
        & py -3.11 -m venv $environmentPath
        if ($LASTEXITCODE -ne 0) { throw 'Creating the Python 3.11 build environment failed.' }
    }
    & $pythonPath -c 'import sys,struct; sys.exit(0 if sys.version_info[:2] == (3,11) and struct.calcsize(chr(80)) == 8 else 1)'
    if ($LASTEXITCODE -ne 0) { throw 'The build needs 64-bit Python 3.11; the existing environment was not modified.' }
    if (-not $SkipInstall) {
        & $pythonPath -m pip install --disable-pip-version-check -r requirements-build.txt
        if ($LASTEXITCODE -ne 0) { throw 'Installing build dependencies failed.' }
    }
    & $pythonPath scripts/build_exe.py --mode $Mode --max-mib 300
    if ($LASTEXITCODE -ne 0) { throw 'Executable build or frozen self-test failed; see build logs.' }
} finally { Pop-Location }
