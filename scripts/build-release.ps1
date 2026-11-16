$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$projectRoot = [IO.Path]::GetFullPath((Get-Location).Path)
& ./scripts/build-playerdata.ps1
& ./scripts/build-bridge.ps1
& ./scripts/build-client.ps1
& ./.venv/Scripts/python.exe scripts/package_server.py
if ($LASTEXITCODE -ne 0) { throw 'Server packaging failed' }
$releaseRoot = Join-Path $projectRoot 'release'
$lines = foreach ($name in @('Aetherloom.exe','Aetherloom-Server.tar.gz')) {
    $digest = (Get-FileHash -LiteralPath (Join-Path $releaseRoot $name) -Algorithm SHA256).Hash.ToLowerInvariant()
    "$digest  $name"
}
[IO.File]::WriteAllLines((Join-Path $releaseRoot 'SHA256SUMS.txt'), $lines, [Text.UTF8Encoding]::new($false))
# Remove generated app artifacts only. Preserve source, worlds, credentials,
# installed Java, dependency caches and published remote release history.
foreach ($relative in @('release/.build','dist','build','bridge/build','playerdata/build')) {
    $target = [IO.Path]::GetFullPath((Join-Path $projectRoot $relative))
    if (-not $target.StartsWith($projectRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Cleanup target escaped project' }
    if (Test-Path -LiteralPath $target) {
        $ancestor = Get-Item -LiteralPath $target
        while ($ancestor.FullName -ne $projectRoot) {
            if ($ancestor.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Refusing to recursively clean through a linked build directory' }
            $ancestor = $ancestor.Parent
            if (-not $ancestor) { throw 'Cleanup ancestry escaped project' }
        }
        Remove-Item -LiteralPath $target -Recurse -Force
    }
}
foreach ($name in @('aetherloom-bridge-0.1.0.jar','aetherloom-playerdata.jar')) {
    $target = Join-Path $projectRoot "assets/$name"
    if (Test-Path -LiteralPath $target) { Remove-Item -LiteralPath $target -Force }
}
foreach ($relative in @('Aetherloom.spec','.local/backups/Aetherloom-Windows-qt.zip')) {
    $target = [IO.Path]::GetFullPath((Join-Path $projectRoot $relative))
    if (-not $target.StartsWith($projectRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Obsolete artifact escaped project' }
    if (Test-Path -LiteralPath $target) {
        $ancestor = (Get-Item -LiteralPath $target).Directory
        while ($ancestor.FullName -ne $projectRoot) {
            if ($ancestor.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Refusing linked artifact cleanup' }
            $ancestor = $ancestor.Parent
            if (-not $ancestor) { throw 'Artifact ancestry escaped project' }
        }
        Remove-Item -LiteralPath $target -Force
    }
}
if (Test-Path -LiteralPath '.local/game-test') {
    foreach ($run in (Get-ChildItem -LiteralPath '.local/game-test' -Directory)) {
        if ($run.Attributes -band [IO.FileAttributes]::ReparsePoint) { continue }
        $mods = Join-Path $run.FullName 'mods'
        if (-not (Test-Path -LiteralPath $mods)) { continue }
        if ((Get-Item -LiteralPath $mods).Attributes -band [IO.FileAttributes]::ReparsePoint) { continue }
        foreach ($name in @('aetherloom-bridge-0.1.0.jar','aetherloom-bridge-0.1.0-fixture.jar')) {
            $copy = [IO.Path]::GetFullPath((Join-Path $mods $name))
            if (-not $copy.StartsWith($projectRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Test artifact escaped project' }
            if (Test-Path -LiteralPath $copy) { Remove-Item -LiteralPath $copy -Force }
        }
    }
}
Write-Output 'Only release/Aetherloom.exe, Aetherloom-Server.tar.gz and SHA256SUMS.txt remain as deliverables.'
