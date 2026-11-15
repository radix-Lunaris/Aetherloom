$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$jdk = $env:JAVA_HOME
if (-not $jdk -or -not (Test-Path "$jdk/bin/javac.exe")) {
    $jdk = (Get-ChildItem .local/jdk17 -Directory | Select-Object -First 1).FullName
}
if (-not $jdk) { throw 'Set JAVA_HOME to a JDK17+ installation' }
New-Item -ItemType Directory -Force playerdata/build/classes,assets | Out-Null
$sources = Get-ChildItem playerdata/src/main/java -Filter *.java -Recurse | ForEach-Object FullName
& "$jdk/bin/javac.exe" --release 17 -encoding UTF-8 -d playerdata/build/classes $sources
if ($LASTEXITCODE -ne 0) { throw 'Player data helper compilation failed' }
& "$jdk/bin/jar.exe" --create --file assets/aetherloom-playerdata.jar --main-class org.sharedplayerdata.core.AetherloomRepair -C playerdata/build/classes .
if ($LASTEXITCODE -ne 0) { throw 'Player data helper packaging failed' }
