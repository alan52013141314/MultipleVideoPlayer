param([switch]$Install)
$ErrorActionPreference='Stop'
$root=$PSScriptRoot
$repo=Split-Path $root
$runtime=Join-Path $root 'runtime'
$download=Join-Path $repo 'downloads'
New-Item -ItemType Directory -Force $runtime,$download | Out-Null
$assets=@(
    @{Name='mpv-dev-x86_64-20261106-git-9028187538.7z';File='libmpv.7z';Hash='B5A3CC91B5DABF88AD5BB21D000834DA4FD0BBDA30F4584D39C082127BD62414'},
    @{Name='ffmpeg-x86_64-git-9f690c6a4.7z';File='ffmpeg.7z';Hash='1F19E71F70AE47D8F48A16C38BCA1C68A42D94A5FDDBDCF1B7AAE8E162B228B8'}
)
foreach($asset in $assets){
    $archive=Join-Path $download $asset.File
    if(!(Test-Path -LiteralPath $archive)){Invoke-WebRequest "https://github.com/shinchiro/mpv-winbuild-cmake/releases/download/20261106/$($asset.Name)" -OutFile $archive}
    if((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ne $asset.Hash){throw "原生元件校驗失敗：$($asset.Name)"}
    & tar -xf $archive -C $runtime
    if($LASTEXITCODE -ne 0){throw '原生元件解壓失敗'}
}
$vulkanArchive=Join-Path $download 'vulkan-runtime.zip'
if(!(Test-Path -LiteralPath $vulkanArchive)){Invoke-WebRequest 'https://sdk.lunarg.com/sdk/download/1.4.363.0/windows/vulkan-runtime-components.zip' -OutFile $vulkanArchive}
if((Get-FileHash -LiteralPath $vulkanArchive -Algorithm SHA256).Hash -ne 'A25A927AA8B9F0371048F1861CF88AC3B9BC9B1FB332C42D897C8AB32695769A'){throw 'Vulkan 元件校驗失敗'}
& tar -xf $vulkanArchive -C $download
if($LASTEXITCODE -ne 0){throw 'Vulkan 元件解壓失敗'}
Copy-Item -LiteralPath (Join-Path $download 'VulkanRT-X64-1.4.363.0-Components\x64\vulkan-1.dll') -Destination $runtime -Force
Push-Location $root
try {
    & cargo build --release --locked --bin multiple-video-player
    if($LASTEXITCODE -ne 0){throw 'Rust 建置失敗'}
    $version=(Select-String -LiteralPath (Join-Path $root 'Cargo.toml') -Pattern '^version = "([^"]+)"').Matches[0].Groups[1].Value
    $name="MultipleVideoPlayer-$version-win64"
    $stage=Join-Path $root "dist\$name"
    New-Item -ItemType Directory -Force $stage,(Join-Path $stage 'runtime'),(Join-Path $stage 'licenses') | Out-Null
    Copy-Item -LiteralPath (Join-Path $root 'target\release\multiple-video-player.exe') -Destination (Join-Path $stage 'MultipleVideoPlayer.exe') -Force
    foreach($file in @('libmpv-2.dll','ffmpeg.exe','vulkan-1.dll')){Copy-Item -LiteralPath (Join-Path $runtime $file) -Destination (Join-Path $stage 'runtime') -Force}
    Copy-Item -LiteralPath (Join-Path $download 'VulkanRT-X64-1.4.363.0-Components\VulkanRT-License.txt') -Destination (Join-Path $stage 'licenses') -Force
    Copy-Item -LiteralPath (Join-Path $repo 'LICENSE'),(Join-Path $repo 'THIRD_PARTY_NOTICES.md'),(Join-Path $root 'README.md') -Destination $stage -Force
    Copy-Item -LiteralPath (Join-Path $root 'native-components.json') -Destination (Join-Path $stage 'licenses') -Force
    $metadata=(& cargo metadata --locked --format-version 1 --filter-platform x86_64-pc-windows-msvc | ConvertFrom-Json)
    if($LASTEXITCODE -ne 0){throw '無法讀取依賴授權'}
    $notices=@()
    foreach($package in $metadata.packages){
        $notices+=[pscustomobject]@{name=$package.name;version=$package.version;license=$package.license;repository=$package.repository}
        $packageRoot=Split-Path $package.manifest_path
        if($packageRoot -eq $root){continue}
        $dest=Join-Path $stage "licenses\$($package.name)-$($package.version)"
        foreach($license in Get-ChildItem -LiteralPath $packageRoot -File -Recurse | Where-Object Name -Match '^(LICENSE|COPYING|NOTICE|UNLICENSE)'){
            $relative=$license.FullName.Substring($packageRoot.Length).TrimStart('\','/')
            $target=Join-Path $dest $relative
            New-Item -ItemType Directory -Force (Split-Path $target) | Out-Null
            Copy-Item -LiteralPath $license.FullName -Destination $target -Force
        }
    }
    $notices | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $stage 'licenses\rust-dependencies.json') -Encoding utf8
    & (Join-Path $runtime 'ffmpeg.exe') -version | Set-Content -LiteralPath (Join-Path $stage 'licenses\ffmpeg-build.txt') -Encoding utf8
    $zip=Join-Path $root "dist\$name.zip"
    # Archive only release files, never personal portable_data.
    & tar -a -cf $zip -C (Split-Path $stage) --exclude=portable_data $name
    if($LASTEXITCODE -ne 0){throw 'ZIP 打包失敗'}
    Get-FileHash -LiteralPath $zip -Algorithm SHA256 | ForEach-Object {"$($_.Hash.ToLower())  $name.zip"} | Set-Content -LiteralPath (Join-Path $root 'dist\SHA256SUMS.txt') -Encoding ascii
    if($Install){
        $release="MultipleVideoPlayer-$version"
        $installed=Join-Path $repo "VideoPlayer\dist\$release"
        New-Item -ItemType Directory -Force $installed | Out-Null
        Copy-Item -Path (Join-Path $stage '*') -Destination $installed -Recurse -Force
        Set-Content -LiteralPath (Join-Path $repo 'VideoPlayer\current-release.txt') -Value $release -Encoding ascii
    }
    Write-Output $zip
}finally{Pop-Location}
