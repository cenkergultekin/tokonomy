$ErrorActionPreference = 'Stop'

$Repo = (Resolve-Path $PSScriptRoot).Path
$CommandDir = Join-Path $HOME '.local\bin'
$Launcher = Join-Path $CommandDir 'tokonomy.cmd'
$Python = (Get-Command python -ErrorAction Stop).Source

New-Item -ItemType Directory -Force -Path $CommandDir | Out-Null
& $Python -m pip install --user --editable $Repo
if ($LASTEXITCODE -ne 0) { throw 'Tokonomy Python package installation failed.' }

@"
@echo off
"$Python" -m tokonomy %*
"@ | Set-Content -LiteralPath $Launcher -Encoding Ascii

$UserPath = [Environment]::GetEnvironmentVariable('Path', 'User')
$PathParts = @($UserPath -split ';' | Where-Object { $_ })
if ($PathParts -notcontains $CommandDir) {
    [Environment]::SetEnvironmentVariable('Path', (@($PathParts) + $CommandDir -join ';'), 'User')
}

Write-Host "Tokonomy installed. Open a new terminal and run: tokonomy"
Write-Host "Launcher: $Launcher"
