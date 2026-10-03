param([string]$PythonPath = (Join-Path $PSScriptRoot '.venv\Scripts\python.exe'))
$ErrorActionPreference = 'Stop'
$playerRoot = $PSScriptRoot
Push-Location (Join-Path $playerRoot 'src')
try {
    $releaseVersion = (& $pythonPath -c 'from gridplayer.workspace_version import VERSION; print(VERSION)').Trim()
    if ($LASTEXITCODE -ne 0 -or $releaseVersion -notmatch '^[0-9A-Za-z.-]+$') { throw 'Invalid release version' }
    & $pythonPath -m PyInstaller --noconfirm --distpath ..\build\release-stage --workpath ..\build workspace.spec
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed' }
} finally { Pop-Location }
$destination = Join-Path $playerRoot 'build\release-stage\GridPlayerWorkspace'
Copy-Item -LiteralPath (Join-Path $playerRoot 'upstream-portable\GridPlayer\libVLC') -Destination $destination -Recurse -Force
New-Item -ItemType Directory -Force (Join-Path $destination 'portable_data') | Out-Null
Copy-Item -LiteralPath (Join-Path $playerRoot 'src\LICENSE') -Destination (Join-Path $destination 'LICENSE-GridPlayer.txt')
Copy-Item -LiteralPath (Join-Path $playerRoot 'README.md') -Destination $destination
Copy-Item -LiteralPath (Join-Path $playerRoot 'SOURCE.txt') -Destination $destination
Copy-Item -LiteralPath (Join-Path $playerRoot '..\THIRD_PARTY_NOTICES.md') -Destination $destination
Copy-Item -LiteralPath (Join-Path $playerRoot '..\licenses') -Destination $destination -Recurse -Force
Copy-Item -LiteralPath (Join-Path $playerRoot 'src\resources\fonts\Hack\LICENSE.md') -Destination (Join-Path $destination 'licenses\Hack-LICENSE.md')
Copy-Item -LiteralPath (Join-Path $playerRoot 'PORTABLE-README.txt') -Destination $destination
$archivePath = Join-Path $playerRoot "GridPlayerWorkspace-$releaseVersion-win64.zip"
Compress-Archive -Path $destination -DestinationPath $archivePath -Force
# Install a new release beside the running one, then switch the small launcher reference.
# The launcher continues using legacy portable_data, so presets are never moved or replaced.
$releaseHash = (Get-FileHash -LiteralPath (Join-Path $destination 'GridPlayerWorkspace.exe') -Algorithm SHA256).Hash.ToLowerInvariant()
$releaseName = 'GridPlayerWorkspace-' + $releaseHash.Substring(0, 12)
$installed = Join-Path (Join-Path $playerRoot 'dist') $releaseName
New-Item -ItemType Directory -Force $installed | Out-Null
Get-ChildItem -LiteralPath $destination | Copy-Item -Destination $installed -Recurse -Force
# Do not switch the launcher until every installed byte matches the staged package.
foreach ($sourceFile in (Get-ChildItem -LiteralPath $destination -Recurse -File)) {
    $relativePath = $sourceFile.FullName.Substring($destination.Length + 1)
    $installedFile = Join-Path $installed $relativePath
    $expectedHash = (Get-FileHash -LiteralPath $sourceFile.FullName -Algorithm SHA256).Hash
    if ((Get-FileHash -LiteralPath $installedFile -Algorithm SHA256).Hash -ne $expectedHash) {
        Copy-Item -LiteralPath $sourceFile.FullName -Destination $installedFile -Force
        if ((Get-FileHash -LiteralPath $installedFile -Algorithm SHA256).Hash -ne $expectedHash) {
            throw "Installed file verification failed: $relativePath"
        }
    }
}
$pendingReference = Join-Path $playerRoot 'current-release.txt.pending'
Set-Content -LiteralPath $pendingReference -Value $releaseName -Encoding ASCII
Move-Item -LiteralPath $pendingReference -Destination (Join-Path $playerRoot 'current-release.txt') -Force
$archiveHash = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant()
Set-Content -LiteralPath (Join-Path $playerRoot 'SHA256SUMS.txt') -Value "$archiveHash  $([IO.Path]::GetFileName($archivePath))" -Encoding ASCII
