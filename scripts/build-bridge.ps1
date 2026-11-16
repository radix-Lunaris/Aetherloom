param([switch]$Offline)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
if (-not $env:JAVA_HOME) {
    $env:JAVA_HOME = (Get-ChildItem .local/jdk17 -Directory | Select-Object -First 1).FullName
}
if (-not (Test-Path "$env:JAVA_HOME/bin/javac.exe")) { throw 'Set JAVA_HOME to JDK17' }
$extra = @()
if ($Offline) { $extra = @('--offline','-Dnet.minecraftforge.gradle.check.certs=false') }
& ./bridge/gradlew.bat -p bridge build --no-daemon --console plain @extra
if ($LASTEXITCODE -ne 0) { throw 'Bridge build failed' }
New-Item -ItemType Directory -Force assets | Out-Null
Copy-Item bridge/build/libs/aetherloom-bridge-0.1.1.jar assets/aetherloom-bridge-0.1.1.jar -Force
