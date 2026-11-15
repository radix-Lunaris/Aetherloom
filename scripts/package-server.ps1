$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$stage = Join-Path (Get-Location) '.local/server-package'
New-Item -ItemType Directory -Force $stage | Out-Null
Copy-Item aetherloom $stage -Recurse -Force
Copy-Item server $stage -Recurse -Force
Copy-Item compose.yaml,.dockerignore,LICENSE,THIRD_PARTY.md,DEPLOY.md $stage -Force
New-Item -ItemType Directory -Force dist | Out-Null
Compress-Archive -Path "$stage/*" -DestinationPath dist/Aetherloom-Server.zip -Force
