$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$projectRoot = [IO.Path]::GetFullPath((Get-Location).Path)
$releaseRoot = Join-Path $projectRoot 'release'
$scratchRoot = Join-Path $releaseRoot '.build'
New-Item -ItemType Directory -Force $scratchRoot | Out-Null
foreach ($jar in @('aetherloom-bridge-0.1.1.jar','aetherloom-playerdata.jar','aetherloom-agent.jar','authlib-injector.jar')) {
    if (-not (Test-Path -LiteralPath (Join-Path $projectRoot "assets/$jar"))) { throw 'Build Bridge and playerdata first, or run scripts/build-release.ps1' }
}
$licensesRoot = Join-Path $scratchRoot 'licenses'
New-Item -ItemType Directory -Force $licensesRoot | Out-Null
Copy-Item LICENSE,THIRD_PARTY.md -Destination $licensesRoot
Copy-Item aetherloom/vendor/authlib/* -Destination $licensesRoot
Copy-Item playerdata/LICENSE.shared-playerdata -Destination $licensesRoot
Copy-Item aetherloom/vendor/craftlink/SOURCE.json -Destination (Join-Path $licensesRoot 'CraftLink-SOURCE.json')
Copy-Item bridge/SOURCE.json -Destination (Join-Path $licensesRoot 'Aetherloom-Bridge-SOURCE.json')
foreach ($package in @('customtkinter-5.2.2.dist-info','websockets-15.0.1.dist-info','pillow-13.0.0.dist-info')) {
    $packageRoot = Join-Path $projectRoot ".venv/Lib/site-packages/$package"
    foreach ($notice in (Get-ChildItem -LiteralPath $packageRoot -Recurse -File | Where-Object { $_.Name -match 'LICENSE|COPYING|METADATA' })) {
        Copy-Item -LiteralPath $notice.FullName -Destination (Join-Path $licensesRoot ($package + '-' + $notice.Name))
    }
}
$pythonBase = (& ./.venv/Scripts/python.exe -c 'import sys;print(sys.base_prefix)').Trim()
if (Test-Path -LiteralPath (Join-Path $pythonBase 'LICENSE.txt')) { Copy-Item -LiteralPath (Join-Path $pythonBase 'LICENSE.txt') -Destination (Join-Path $licensesRoot 'Python-LICENSE.txt') }
foreach ($library in @('tcl8.6','tk8.6')) {
    $notice = Join-Path $pythonBase "tcl/$library/license.terms"
    if (Test-Path -LiteralPath $notice) { Copy-Item -LiteralPath $notice -Destination (Join-Path $licensesRoot "$library-license.terms") }
}
$version = (& ./.venv/Scripts/python.exe -c "import tomllib;print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])").Trim()
$sourceCommit = (& git rev-parse HEAD).Trim()
$buildInfo = @{ version = $version; source_commit = $sourceCommit; built_utc = [DateTime]::UtcNow.ToString('o'); platform = 'Windows-x64'; bundled_java = $false }
$infoPath = Join-Path $scratchRoot 'BUILD_INFO.json'
[IO.File]::WriteAllText($infoPath, ($buildInfo | ConvertTo-Json), [Text.UTF8Encoding]::new($false))
$assetsRoot = Join-Path $projectRoot 'assets'
& ./.venv/Scripts/python.exe -m PyInstaller --noconfirm --windowed --onefile --name Aetherloom --distpath $releaseRoot --workpath (Join-Path $scratchRoot 'pyinstaller') --specpath $scratchRoot --collect-all customtkinter --exclude-module PySide6 --exclude-module PyQt6 --add-data "$assetsRoot;assets" --add-data "$licensesRoot;licenses" --add-data "$infoPath;." (Join-Path $projectRoot 'desktop.py')
if ($LASTEXITCODE -ne 0) { throw 'Client build failed; previous outputs and diagnostics retained' }
Write-Output (Join-Path $releaseRoot 'Aetherloom.exe')
