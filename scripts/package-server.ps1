$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
& python scripts/package_server.py
if ($LASTEXITCODE -ne 0) { throw 'Server packaging failed' }
