$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
& .\.venv\Scripts\python.exe -m PyInstaller --noconfirm --windowed --onedir --name Aetherloom --exclude-module PySide6.QtWebEngineCore --exclude-module PySide6.QtWebEngineWidgets desktop.py
if ($LASTEXITCODE -ne 0) { throw 'Build failed' }
Copy-Item LICENSE,THIRD_PARTY.md,DEPLOY.md,BUILD.md dist\Aetherloom
if (-not (Test-Path runtime\bin\java.exe)) { throw 'Place Temurin Java17 JRE in runtime first' }
Copy-Item runtime dist\Aetherloom\runtime -Recurse -Force
New-Item -ItemType Directory -Force dist\Aetherloom\licenses | Out-Null
Copy-Item .venv\Lib\site-packages\pyside6-6.10.1.dist-info\METADATA dist\Aetherloom\licenses\PySide6-METADATA.txt
Copy-Item .venv\Lib\site-packages\pyside6-6.10.1.dist-info\licenses dist\Aetherloom\licenses\PySide6 -Recurse -Force
Compress-Archive -Path dist\Aetherloom\* -DestinationPath dist\Aetherloom-Windows.zip -Force

