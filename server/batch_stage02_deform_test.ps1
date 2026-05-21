param(
    [Parameter(Mandatory = $true)]
    [string]$SourceMax,

    [string]$AssetName = "",

    [string]$OutDir = "",

    [string]$MaxBatch = "D:\Program files\Autodesk\3ds Max 2020\3dsmaxbatch.exe"
)

$ErrorActionPreference = "Stop"

$ToolRoot = Split-Path -Parent $PSScriptRoot
$BatchScript = Join-Path $ToolRoot "maxscript\batch_stage02_deform_test.ms"

if (-not (Test-Path -LiteralPath $SourceMax)) {
    throw "Source Stage02 MAX scene not found: $SourceMax"
}

if (-not (Test-Path -LiteralPath $BatchScript)) {
    throw "Stage02 deformation batch MaxScript not found: $BatchScript"
}

if (-not (Test-Path -LiteralPath $MaxBatch)) {
    throw "3dsmaxbatch.exe not found: $MaxBatch"
}

if ([string]::IsNullOrWhiteSpace($AssetName)) {
    $AssetName = [System.IO.Path]::GetFileNameWithoutExtension($SourceMax)
    $AssetName = $AssetName -replace '_stage02_skin_scene$', ''
}

$SafeAssetName = ($AssetName -replace '[\\/:*?"<>|]', '_')
if ([string]::IsNullOrWhiteSpace($OutDir)) {
    $OutRoot = Join-Path $ToolRoot "out\stage02_deform_tests"
}
else {
    $OutRoot = $OutDir
}

$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$RunDir = Join-Path $OutRoot "$SafeAssetName`__${Timestamp}"

New-Item -ItemType Directory -Force -Path (Join-Path $RunDir "reports") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $RunDir "data") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $RunDir "logs") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $RunDir "screenshots") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $RunDir "posed_scenes") | Out-Null

$oldSourceMax = [Environment]::GetEnvironmentVariable("AIRA_STAGE02_DEFORM_SOURCE_MAX", "Process")
$oldAssetName = [Environment]::GetEnvironmentVariable("AIRA_STAGE02_ASSET_NAME", "Process")
$oldOutDir = [Environment]::GetEnvironmentVariable("AIRA_STAGE02_DEFORM_OUT_DIR", "Process")
$BatchReturnCode = 0

try {
    $env:AIRA_STAGE02_DEFORM_SOURCE_MAX = (Resolve-Path -LiteralPath $SourceMax).Path
    $env:AIRA_STAGE02_ASSET_NAME = $SafeAssetName
    $env:AIRA_STAGE02_DEFORM_OUT_DIR = $RunDir

    & $MaxBatch $BatchScript `
        -v 4 `
        -log (Join-Path $RunDir "logs\$SafeAssetName`_stage02_deform_3dsmaxbatch.log") `
        -listenerlog (Join-Path $RunDir "logs\$SafeAssetName`_stage02_deform_listener.log")
    $BatchReturnCode = $LASTEXITCODE
    if ($BatchReturnCode -ne 0) {
        throw "3dsmaxbatch Stage02 deformation test failed with exit code $BatchReturnCode. See logs in $RunDir\logs."
    }
}
finally {
    if ($null -eq $oldSourceMax) { Remove-Item Env:AIRA_STAGE02_DEFORM_SOURCE_MAX -ErrorAction SilentlyContinue } else { $env:AIRA_STAGE02_DEFORM_SOURCE_MAX = $oldSourceMax }
    if ($null -eq $oldAssetName) { Remove-Item Env:AIRA_STAGE02_ASSET_NAME -ErrorAction SilentlyContinue } else { $env:AIRA_STAGE02_ASSET_NAME = $oldAssetName }
    if ($null -eq $oldOutDir) { Remove-Item Env:AIRA_STAGE02_DEFORM_OUT_DIR -ErrorAction SilentlyContinue } else { $env:AIRA_STAGE02_DEFORM_OUT_DIR = $oldOutDir }
}

$Result = [ordered]@{
    ok = $true
    assetName = $SafeAssetName
    sourceMax = (Resolve-Path -LiteralPath $SourceMax).Path
    runDir = $RunDir
    reportJson = Join-Path $RunDir "data\$SafeAssetName`_stage02_deform_test_report.json"
    reportMarkdown = Join-Path $RunDir "reports\$SafeAssetName`_stage02_deform_test_report.md"
    summary = Join-Path $RunDir "reports\$SafeAssetName`_stage02_deform_batch_summary.md"
    screenshots = Join-Path $RunDir "screenshots"
    posedScenes = Join-Path $RunDir "posed_scenes"
    batchReturnCode = $BatchReturnCode
}

$Result | ConvertTo-Json -Depth 6
