$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
& .\.venv\Scripts\python.exe -m PyInstaller --noconfirm --windowed --onedir --name Aetherloom --collect-all customtkinter --exclude-module PySide6 --exclude-module PyQt6 desktop.py
if ($LASTEXITCODE -ne 0) { throw 'Build failed' }
Copy-Item LICENSE,THIRD_PARTY.md,DEPLOY.md,BUILD.md dist\Aetherloom
if (-not (Test-Path runtime\bin\java.exe)) { throw 'Place Temurin Java17 JRE in runtime first' }
Copy-Item runtime dist\Aetherloom\runtime -Recurse -Force
New-Item -ItemType Directory -Force dist\Aetherloom\licenses | Out-Null
$licenseFiles = Get-ChildItem .venv\Lib\site-packages\customtkinter-5.2.2.dist-info -Recurse -File | Where-Object { $_.Name -match 'LICENSE|METADATA' }
foreach ($item in $licenseFiles) { Copy-Item -LiteralPath $item.FullName -Destination (Join-Path dist\Aetherloom\licenses ('CustomTkinter-' + $item.Name)) }
Compress-Archive -Path dist\Aetherloom\* -DestinationPath dist\Aetherloom-Windows.zip -Force

