param(
    [Parameter(Mandatory = $true)]
    [string]$SourceFbx,

    [string]$AssetName = "",

    [string]$OutDir = "",

    [string]$MaxBatch = ""
)

$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "aira_config.ps1")

$AiraConfig = Set-AiraProcessEnvironmentFromConfig
$ToolRoot = $AiraConfig.toolRoot
$BatchScript = Join-Path $ToolRoot "maxscript\batch_asset_qc_fbx.ms"
$MaxBatch = Get-AiraMaxBatch $MaxBatch

if (-not (Test-Path -LiteralPath $MaxBatch -PathType Leaf)) {
    throw "3dsmaxbatch.exe not found: $MaxBatch. Run server\setup_local.ps1 or set AIRA_MAXBATCH."
}

if (-not (Test-Path -LiteralPath $SourceFbx)) {
    throw "FBX file not found: $SourceFbx"
}

if ([string]::IsNullOrWhiteSpace($AssetName)) {
    $AssetName = [System.IO.Path]::GetFileNameWithoutExtension($SourceFbx)
}

$SafeAssetName = ($AssetName -replace '[\\/:*?"<>|]', '_')
if ([string]::IsNullOrWhiteSpace($OutDir)) {
    $OutDir = Get-AiraOutDir
}

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

function Copy-FbxTextureSidecar {
    param(
        [Parameter(Mandatory = $true)]
        [string]$SourceFbxPath,

        [Parameter(Mandatory = $true)]
        [string]$WorkingFbxPath
    )

    $SourceDir = Split-Path -Parent $SourceFbxPath
    $SourceBaseName = [System.IO.Path]::GetFileNameWithoutExtension($SourceFbxPath)
    $WorkingDir = Split-Path -Parent $WorkingFbxPath
    $WorkingBaseName = [System.IO.Path]::GetFileNameWithoutExtension($WorkingFbxPath)
    $SourceSidecar = Join-Path $SourceDir "$SourceBaseName.fbm"
    $WorkingSidecar = Join-Path $WorkingDir "$WorkingBaseName.fbm"

    if (-not (Test-Path -LiteralPath $SourceSidecar -PathType Container)) {
        return ""
    }

    New-Item -ItemType Directory -Force -Path $WorkingSidecar | Out-Null
    Get-ChildItem -LiteralPath $SourceSidecar -Force | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination $WorkingSidecar -Recurse -Force
    }
    return $WorkingSidecar
}

# 3ds Max 2020 / MAXScript is much happier when the import path is ASCII-only.
$WorkingFbx = Join-Path $OutDir "$SafeAssetName.fbx"
Copy-Item -LiteralPath $SourceFbx -Destination $WorkingFbx -Force
$TextureSidecar = Copy-FbxTextureSidecar -SourceFbxPath $SourceFbx -WorkingFbxPath $WorkingFbx

$oldFbxPath = [Environment]::GetEnvironmentVariable("AIRA_QC_FBX_PATH", "Process")
$oldAssetName = [Environment]::GetEnvironmentVariable("AIRA_QC_ASSET_NAME", "Process")
$oldTextureDir = [Environment]::GetEnvironmentVariable("AIRA_QC_TEXTURE_DIR", "Process")
$oldOutDir = [Environment]::GetEnvironmentVariable("AIRA_QC_OUT_DIR", "Process")

try {
    $env:AIRA_QC_FBX_PATH = $WorkingFbx
    $env:AIRA_QC_ASSET_NAME = $SafeAssetName
    $env:AIRA_QC_TEXTURE_DIR = $TextureSidecar
    $env:AIRA_QC_OUT_DIR = $OutDir

    & $MaxBatch $BatchScript `
        -v 4 `
        -log (Join-Path $OutDir "$SafeAssetName`_asset_qc_3dsmaxbatch.log") `
        -listenerlog (Join-Path $OutDir "$SafeAssetName`_asset_qc_listener.log")
}
finally {
    if ($null -eq $oldFbxPath) {
        Remove-Item Env:AIRA_QC_FBX_PATH -ErrorAction SilentlyContinue
    }
    else {
        $env:AIRA_QC_FBX_PATH = $oldFbxPath
    }

    if ($null -eq $oldAssetName) {
        Remove-Item Env:AIRA_QC_ASSET_NAME -ErrorAction SilentlyContinue
    }
    else {
        $env:AIRA_QC_ASSET_NAME = $oldAssetName
    }

    if ($null -eq $oldTextureDir) {
        Remove-Item Env:AIRA_QC_TEXTURE_DIR -ErrorAction SilentlyContinue
    }
    else {
        $env:AIRA_QC_TEXTURE_DIR = $oldTextureDir
    }

    if ($null -eq $oldOutDir) {
        Remove-Item Env:AIRA_QC_OUT_DIR -ErrorAction SilentlyContinue
    }
    else {
        $env:AIRA_QC_OUT_DIR = $oldOutDir
    }
}

$JsonPath = Join-Path $OutDir "$SafeAssetName`_asset_qc.json"
$MarkdownPath = Join-Path $OutDir "$SafeAssetName`_asset_qc.md"
$ScenePath = Join-Path $OutDir "$SafeAssetName`_raw_asset_qc_scene.max"

[pscustomobject]@{
    ok = (Test-Path -LiteralPath $JsonPath)
    sourceFbx = $SourceFbx
    workingFbx = $WorkingFbx
    textureSidecar = $TextureSidecar
    assetName = $SafeAssetName
    json = $JsonPath
    markdown = $MarkdownPath
    scene = $ScenePath
} | ConvertTo-Json -Depth 4
