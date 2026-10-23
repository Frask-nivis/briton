$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
function Invoke-Checked {
    param([string]$Exe, [string[]]$Arguments)
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Perintah gagal: $Exe $Arguments" }
}
if (Get-Command py -ErrorAction SilentlyContinue) {
    $Bootstrap = 'py'; $Prefix = @('-3')
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $Bootstrap = 'python'; $Prefix = @()
} else { throw 'Install Python 3.10+ dari python.org, lalu buka ulang terminal.' }
Invoke-Checked -Exe $Bootstrap -Arguments ($Prefix + @('-c', 'import sys; assert sys.version_info >= (3,10), "Butuh Python 3.10+"'))
if (!(Test-Path '.venv/Scripts/python.exe')) {
    Invoke-Checked -Exe $Bootstrap -Arguments ($Prefix + @('-m', 'venv', '.venv'))
}
$Python = Join-Path $PWD '.venv/Scripts/python.exe'
Invoke-Checked -Exe $Python -Arguments @('-m', 'pip', 'install', '-r', 'requirements.txt')
Invoke-Checked -Exe $Python -Arguments @('-m', 'playwright', 'install', 'chromium')
foreach ($Folder in @('answers', 'captures', 'outputs')) {
    New-Item -ItemType Directory -Force -Path $Folder | Out-Null
}
if (!(Test-Path 'config/ai.local.json')) { Copy-Item 'config/ai.example.json' 'config/ai.local.json' }
if (!(Test-Path 'answers/match817.json')) { Copy-Item 'examples/match817.example.json' 'answers/match817.json' }
Write-Host 'Setup selesai. AI masih template, tidak aktif.'
Write-Host 'Login: .\.venv\Scripts\python.exe briton.py login'
