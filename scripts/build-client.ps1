$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
& .\.venv\Scripts\python.exe -m PyInstaller --noconfirm --windowed --onedir --name Aetherloom --collect-all customtkinter --exclude-module PySide6 --exclude-module PyQt6 desktop.py
if ($LASTEXITCODE -ne 0) { throw 'Build failed' }
Copy-Item LICENSE,THIRD_PARTY.md,DEPLOY.md,BUILD.md,PLAY.md dist\Aetherloom
# Runtime is supplied by the player's game environment, never bundled.
# Remove only this obsolete artifact if building over a previous distribution.
$clientOutput = [IO.Path]::GetFullPath((Join-Path (Get-Location) 'dist/Aetherloom'))
$obsoleteRuntime = [IO.Path]::GetFullPath((Join-Path $clientOutput 'runtime'))
if ((Split-Path $obsoleteRuntime -Parent) -ne $clientOutput) { throw 'Invalid runtime artifact path' }
if (Test-Path -LiteralPath $obsoleteRuntime) { Remove-Item -LiteralPath $obsoleteRuntime -Recurse -Force }
Copy-Item assets dist\Aetherloom\assets -Recurse -Force
Copy-Item playerdata\LICENSE.shared-playerdata dist\Aetherloom\LICENSE.shared-playerdata
Copy-Item aetherloom\vendor\craftlink\SOURCE.json dist\Aetherloom\CraftLink-SOURCE.json
New-Item -ItemType Directory -Force dist\Aetherloom\licenses | Out-Null
$licenseFiles = Get-ChildItem .venv\Lib\site-packages\customtkinter-5.2.2.dist-info -Recurse -File | Where-Object { $_.Name -match 'LICENSE|METADATA' }
foreach ($item in $licenseFiles) { Copy-Item -LiteralPath $item.FullName -Destination (Join-Path dist\Aetherloom\licenses ('CustomTkinter-' + $item.Name)) }
foreach ($package in @('websockets-15.0.1.dist-info','pillow-13.0.0.dist-info')) {
    $notices = Get-ChildItem (Join-Path .venv\Lib\site-packages $package) -Recurse -File | Where-Object { $_.Name -match 'LICENSE|COPYING' }
    foreach ($item in $notices) { Copy-Item -LiteralPath $item.FullName -Destination (Join-Path dist\Aetherloom\licenses ($package + '-' + $item.Name)) }
}
$version = (& .\.venv\Scripts\python.exe -c "import tomllib;print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])").Trim()
$sourceCommit = (& git rev-parse HEAD).Trim()
$buildInfo = @{ version = $version; source_commit = $sourceCommit; built_utc = [DateTime]::UtcNow.ToString('o'); platform = 'Windows-x64' } | ConvertTo-Json
[System.IO.File]::WriteAllText((Join-Path (Get-Location) 'dist/Aetherloom/BUILD_INFO.json'), $buildInfo, [System.Text.UTF8Encoding]::new($false))
Compress-Archive -Path dist\Aetherloom\* -DestinationPath dist\Aetherloom-Windows.zip -Force

