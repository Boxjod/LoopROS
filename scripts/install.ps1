# Run from a downloaded source checkout; no administrator privileges required.
$ErrorActionPreference = 'Stop'
$installer = Join-Path $PSScriptRoot 'install.py'
$sourceRoot = Split-Path -Parent $PSScriptRoot
$existingPython = Join-Path $sourceRoot '.venv\Scripts\python.exe'
if ($env:LOOP_PYTHON) {
    & $env:LOOP_PYTHON $installer @args
} elseif (Test-Path $existingPython) {
    & $existingPython $installer @args
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 $installer @args
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    & python $installer @args
} else {
    throw 'Install an OS-compatible Python 3.8+ for the uv bootstrap, then rerun. Windows 7/8 require remote SSH access.'
}
exit $LASTEXITCODE
