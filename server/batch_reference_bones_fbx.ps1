param(
    [Parameter(Mandatory = $true)]
    [string]$ReferenceFbx,

    [string]$AssetName = "",

    [string]$OutDir = ""
)

$ErrorActionPreference = "Stop"

$ToolRoot = "F:\workspace\github\3dsmax-ai-rig-assistant"
$BatchScript = Join-Path $ToolRoot "maxscript\batch_reference_bones_fbx.ms"
$MaxBatch = "D:\Program files\Autodesk\3ds Max 2020\3dsmaxbatch.exe"

if (-not (Test-Path -LiteralPath $ReferenceFbx)) {
    throw "Reference FBX file not found: $ReferenceFbx"
}

if ([string]::IsNullOrWhiteSpace($AssetName)) {
    $AssetName = [System.IO.Path]::GetFileNameWithoutExtension($ReferenceFbx)
}

$SafeAssetName = ($AssetName -replace '[\\/:*?"<>|]', '_')
if ([string]::IsNullOrWhiteSpace($OutDir)) {
    $OutDir = Join-Path $ToolRoot "out\reference_bones\$SafeAssetName"
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
