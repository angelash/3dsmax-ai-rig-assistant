param(
    [Parameter(Mandatory = $true)]
    [string]$ReferenceFbx,

    [string]$AssetName = "",

    [string]$OutDir = "",

    [string]$MaxBatch = ""
)

$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "aira_config.ps1")

$AiraConfig = Set-AiraProcessEnvironmentFromConfig
$ToolRoot = $AiraConfig.toolRoot
$BatchScript = Join-Path $ToolRoot "maxscript\batch_reference_bones_fbx.ms"
$MaxBatch = Get-AiraMaxBatch $MaxBatch

if (-not (Test-Path -LiteralPath $MaxBatch -PathType Leaf)) {
    throw "3dsmaxbatch.exe not found: $MaxBatch. Run server\setup_local.ps1 or set AIRA_MAXBATCH."
}

if (-not (Test-Path -LiteralPath $ReferenceFbx)) {
    throw "Reference FBX file not found: $ReferenceFbx"
}

if ([string]::IsNullOrWhiteSpace($AssetName)) {
    $AssetName = [System.IO.Path]::GetFileNameWithoutExtension($ReferenceFbx)
}

$SafeAssetName = ($AssetName -replace '[\\/:*?"<>|]', '_')
if ([string]::IsNullOrWhiteSpace($OutDir)) {
    $OutDir = Join-Path (Get-AiraOutDir) "reference_bones\$SafeAssetName"
}

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

# 3ds Max 2020/MAXScript imports are much more reliable from ASCII paths.
$WorkingFbx = Join-Path $OutDir "$SafeAssetName`_reference.fbx"
Copy-Item -LiteralPath $ReferenceFbx -Destination $WorkingFbx -Force

$oldFbxPath = [Environment]::GetEnvironmentVariable("AIRA_REF_FBX_PATH", "Process")
$oldAssetName = [Environment]::GetEnvironmentVariable("AIRA_REF_ASSET_NAME", "Process")
$oldOutDir = [Environment]::GetEnvironmentVariable("AIRA_REF_OUT_DIR", "Process")

try {
    $env:AIRA_REF_FBX_PATH = $WorkingFbx
    $env:AIRA_REF_ASSET_NAME = $SafeAssetName
    $env:AIRA_REF_OUT_DIR = $OutDir

    & $MaxBatch $BatchScript `
        -v 4 `
        -log (Join-Path $OutDir "$SafeAssetName`_reference_bones_3dsmaxbatch.log") `
        -listenerlog (Join-Path $OutDir "$SafeAssetName`_reference_bones_listener.log")
}
finally {
    if ($null -eq $oldFbxPath) {
        Remove-Item Env:AIRA_REF_FBX_PATH -ErrorAction SilentlyContinue
    }
    else {
        $env:AIRA_REF_FBX_PATH = $oldFbxPath
    }

    if ($null -eq $oldAssetName) {
        Remove-Item Env:AIRA_REF_ASSET_NAME -ErrorAction SilentlyContinue
    }
    else {
        $env:AIRA_REF_ASSET_NAME = $oldAssetName
    }

    if ($null -eq $oldOutDir) {
        Remove-Item Env:AIRA_REF_OUT_DIR -ErrorAction SilentlyContinue
    }
    else {
        $env:AIRA_REF_OUT_DIR = $oldOutDir
    }
}

$JsonPath = Join-Path $OutDir "$SafeAssetName`_reference_bones.json"

[pscustomobject]@{
    ok = (Test-Path -LiteralPath $JsonPath)
    referenceFbx = $ReferenceFbx
    workingFbx = $WorkingFbx
    assetName = $SafeAssetName
    json = $JsonPath
} | ConvertTo-Json -Depth 4
