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
$BatchScript = Join-Path $ToolRoot "maxscript\batch_export_fbx_obj.ms"
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
$WorkingFbx = Join-Path $OutDir "$SafeAssetName.fbx"
Copy-Item -LiteralPath $SourceFbx -Destination $WorkingFbx -Force

$oldFbxPath = [Environment]::GetEnvironmentVariable("AIRA_EXPORT_FBX_PATH", "Process")
$oldAssetName = [Environment]::GetEnvironmentVariable("AIRA_EXPORT_ASSET_NAME", "Process")
$oldOutDir = [Environment]::GetEnvironmentVariable("AIRA_EXPORT_OUT_DIR", "Process")

try {
    $env:AIRA_EXPORT_FBX_PATH = $WorkingFbx
    $env:AIRA_EXPORT_ASSET_NAME = $SafeAssetName
    $env:AIRA_EXPORT_OUT_DIR = $OutDir

    & $MaxBatch $BatchScript `
        -v 4 `
        -log (Join-Path $OutDir "$SafeAssetName`_export_obj_3dsmaxbatch.log") `
        -listenerlog (Join-Path $OutDir "$SafeAssetName`_export_obj_listener.log")
}
finally {
    if ($null -eq $oldFbxPath) {
        Remove-Item Env:AIRA_EXPORT_FBX_PATH -ErrorAction SilentlyContinue
    }
    else {
        $env:AIRA_EXPORT_FBX_PATH = $oldFbxPath
    }

    if ($null -eq $oldAssetName) {
        Remove-Item Env:AIRA_EXPORT_ASSET_NAME -ErrorAction SilentlyContinue
    }
    else {
        $env:AIRA_EXPORT_ASSET_NAME = $oldAssetName
    }

    if ($null -eq $oldOutDir) {
        Remove-Item Env:AIRA_EXPORT_OUT_DIR -ErrorAction SilentlyContinue
    }
    else {
        $env:AIRA_EXPORT_OUT_DIR = $oldOutDir
    }
}

[pscustomobject]@{
    ok = (Test-Path -LiteralPath (Join-Path $OutDir "$SafeAssetName.obj"))
    sourceFbx = $SourceFbx
    workingFbx = $WorkingFbx
    assetName = $SafeAssetName
    obj = Join-Path $OutDir "$SafeAssetName.obj"
} | ConvertTo-Json -Depth 4
