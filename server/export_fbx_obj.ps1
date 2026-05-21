param(
    [Parameter(Mandatory = $true)]
    [string]$SourceFbx,

    [string]$AssetName = "",

    [string]$OutDir = ""
)

$ErrorActionPreference = "Stop"

$RepoRoot = "F:\workspace\open-share"
$ToolRoot = "F:\workspace\github\3dsmax-ai-rig-assistant"
$BatchScript = Join-Path $ToolRoot "maxscript\batch_export_fbx_obj.ms"
$MaxBatch = "D:\Program files\Autodesk\3ds Max 2020\3dsmaxbatch.exe"

if (-not (Test-Path -LiteralPath $SourceFbx)) {
    throw "FBX file not found: $SourceFbx"
}

if ([string]::IsNullOrWhiteSpace($AssetName)) {
    $AssetName = [System.IO.Path]::GetFileNameWithoutExtension($SourceFbx)
}

$SafeAssetName = ($AssetName -replace '[\\/:*?"<>|]', '_')
if ([string]::IsNullOrWhiteSpace($OutDir)) {
    $OutDir = Join-Path $ToolRoot "out"
}

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$WorkingFbx = Join-Path $OutDir "$SafeAssetName.fbx"
Copy-Item -LiteralPath $SourceFbx -Destination $WorkingFbx -Force

$oldFbxPath = [Environment]::GetEnvironmentVariable("AIRA_EXPORT_FBX_PATH", "Process")
$oldAssetName = [Environment]::GetEnvironmentVariable("AIRA_EXPORT_ASSET_NAME", "Process")

try {
    $env:AIRA_EXPORT_FBX_PATH = $WorkingFbx
    $env:AIRA_EXPORT_ASSET_NAME = $SafeAssetName

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
}

[pscustomobject]@{
    ok = (Test-Path -LiteralPath (Join-Path $OutDir "$SafeAssetName.obj"))
    sourceFbx = $SourceFbx
    workingFbx = $WorkingFbx
    assetName = $SafeAssetName
    obj = Join-Path $OutDir "$SafeAssetName.obj"
} | ConvertTo-Json -Depth 4
