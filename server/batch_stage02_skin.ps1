param(
    [Parameter(Mandatory = $true)]
    [string]$SourceMax,

    [string]$AssetName = "",

    [string]$Stage01SkinPrepGateJson = "",

    [switch]$AllowBlockedStage01,

    [ValidateRange(1, 4)]
    [int]$BoneAffectLimit = 3,

    [string]$OutDir = "",

    [string]$MaxBatch = "D:\Program files\Autodesk\3ds Max 2020\3dsmaxbatch.exe"
)

$ErrorActionPreference = "Stop"

$ToolRoot = Split-Path -Parent $PSScriptRoot
$BatchScript = Join-Path $ToolRoot "maxscript\batch_stage02_skin.ms"

if (-not (Test-Path -LiteralPath $SourceMax)) {
    throw "Source MAX scene not found: $SourceMax"
}

if (-not (Test-Path -LiteralPath $BatchScript)) {
    throw "Stage02 batch MaxScript not found: $BatchScript"
}

if (-not (Test-Path -LiteralPath $MaxBatch)) {
    throw "3dsmaxbatch.exe not found: $MaxBatch"
}

if ([string]::IsNullOrWhiteSpace($AssetName)) {
    $AssetName = [System.IO.Path]::GetFileNameWithoutExtension($SourceMax)
    $AssetName = $AssetName -replace '_stage01_rig_scene$', ''
}

$SafeAssetName = ($AssetName -replace '[\\/:*?"<>|]', '_')
if ([string]::IsNullOrWhiteSpace($OutDir)) {
    $OutRoot = Join-Path $ToolRoot "out\stage02_runs"
}
else {
    $OutRoot = $OutDir
}

$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$RunDir = Join-Path $OutRoot "$SafeAssetName`__$Timestamp"

$Stage01GateStatus = "not_provided"
$Stage01GateReady = $false
$ResolvedGateJson = ""

if (-not [string]::IsNullOrWhiteSpace($Stage01SkinPrepGateJson)) {
    if (-not (Test-Path -LiteralPath $Stage01SkinPrepGateJson)) {
        throw "Stage01 Skin Prep Gate JSON not found: $Stage01SkinPrepGateJson"
    }

    $ResolvedGateJson = (Resolve-Path -LiteralPath $Stage01SkinPrepGateJson).Path
    $Gate = Get-Content -LiteralPath $ResolvedGateJson -Raw | ConvertFrom-Json
    $Stage01GateReady = ($Gate.skinSetupReady -eq $true)
    $Stage01GateStatus = if ($Stage01GateReady) { "skin_setup_ready" } else { "blocked_by_stage01_skin_prep_gate" }
}

if (-not $Stage01GateReady) {
    if ($AllowBlockedStage01.IsPresent) {
        if ($Stage01GateStatus -eq "not_provided") {
            $Stage01GateStatus = "forced_research_only_no_stage01_gate"
        }
        else {
            $Stage01GateStatus = "forced_research_only_blocked_stage01_gate"
        }
    }
    else {
        throw "Stage02 Skin setup requires a Stage01 gate with skinSetupReady=true. Pass -AllowBlockedStage01 only for research/first-pass experiments; the output will remain non-production."
    }
}

New-Item -ItemType Directory -Force -Path (Join-Path $RunDir "scene") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $RunDir "reports") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $RunDir "data") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $RunDir "logs") | Out-Null

$oldSourceMax = [Environment]::GetEnvironmentVariable("AIRA_STAGE02_SOURCE_MAX", "Process")
$oldAssetName = [Environment]::GetEnvironmentVariable("AIRA_STAGE02_ASSET_NAME", "Process")
$oldOutDir = [Environment]::GetEnvironmentVariable("AIRA_STAGE02_OUT_DIR", "Process")
$oldAffectLimit = [Environment]::GetEnvironmentVariable("AIRA_STAGE02_BONE_AFFECT_LIMIT", "Process")
$oldGateStatus = [Environment]::GetEnvironmentVariable("AIRA_STAGE02_STAGE01_GATE_STATUS", "Process")
$oldGateJson = [Environment]::GetEnvironmentVariable("AIRA_STAGE02_STAGE01_GATE_JSON", "Process")
$BatchReturnCode = 0

try {
    $env:AIRA_STAGE02_SOURCE_MAX = (Resolve-Path -LiteralPath $SourceMax).Path
    $env:AIRA_STAGE02_ASSET_NAME = $SafeAssetName
    $env:AIRA_STAGE02_OUT_DIR = $RunDir
    $env:AIRA_STAGE02_BONE_AFFECT_LIMIT = [string]$BoneAffectLimit
    $env:AIRA_STAGE02_STAGE01_GATE_STATUS = $Stage01GateStatus
    $env:AIRA_STAGE02_STAGE01_GATE_JSON = $ResolvedGateJson

    & $MaxBatch $BatchScript `
        -v 4 `
        -log (Join-Path $RunDir "logs\$SafeAssetName`_stage02_3dsmaxbatch.log") `
        -listenerlog (Join-Path $RunDir "logs\$SafeAssetName`_stage02_listener.log")
    $BatchReturnCode = $LASTEXITCODE
    if ($BatchReturnCode -ne 0) {
        throw "3dsmaxbatch Stage02 failed with exit code $BatchReturnCode. See logs in $RunDir\logs."
    }
}
finally {
    if ($null -eq $oldSourceMax) { Remove-Item Env:AIRA_STAGE02_SOURCE_MAX -ErrorAction SilentlyContinue } else { $env:AIRA_STAGE02_SOURCE_MAX = $oldSourceMax }
    if ($null -eq $oldAssetName) { Remove-Item Env:AIRA_STAGE02_ASSET_NAME -ErrorAction SilentlyContinue } else { $env:AIRA_STAGE02_ASSET_NAME = $oldAssetName }
    if ($null -eq $oldOutDir) { Remove-Item Env:AIRA_STAGE02_OUT_DIR -ErrorAction SilentlyContinue } else { $env:AIRA_STAGE02_OUT_DIR = $oldOutDir }
    if ($null -eq $oldAffectLimit) { Remove-Item Env:AIRA_STAGE02_BONE_AFFECT_LIMIT -ErrorAction SilentlyContinue } else { $env:AIRA_STAGE02_BONE_AFFECT_LIMIT = $oldAffectLimit }
    if ($null -eq $oldGateStatus) { Remove-Item Env:AIRA_STAGE02_STAGE01_GATE_STATUS -ErrorAction SilentlyContinue } else { $env:AIRA_STAGE02_STAGE01_GATE_STATUS = $oldGateStatus }
    if ($null -eq $oldGateJson) { Remove-Item Env:AIRA_STAGE02_STAGE01_GATE_JSON -ErrorAction SilentlyContinue } else { $env:AIRA_STAGE02_STAGE01_GATE_JSON = $oldGateJson }
}

$Result = [ordered]@{
    ok = $true
    assetName = $SafeAssetName
    sourceMax = (Resolve-Path -LiteralPath $SourceMax).Path
    runDir = $RunDir
    stage01GateStatus = $Stage01GateStatus
    stage01SkinPrepGateJson = $ResolvedGateJson
    boneAffectLimit = $BoneAffectLimit
    scene = Join-Path $RunDir "scene\$SafeAssetName`_stage02_skin_scene.max"
    summary = Join-Path $RunDir "reports\$SafeAssetName`_stage02_batch_summary.md"
    stage02SkinReportJson = Join-Path $RunDir "data\$SafeAssetName`_stage02_skin_report.json"
    stage02SkinReportMarkdown = Join-Path $RunDir "reports\$SafeAssetName`_stage02_skin_report.md"
    stage02AssetQcJson = Join-Path $RunDir "data\$SafeAssetName`_stage02_skin_asset_qc.json"
    stage02AssetQcMarkdown = Join-Path $RunDir "data\$SafeAssetName`_stage02_skin_asset_qc.md"
    batchReturnCode = $BatchReturnCode
}

$Result | ConvertTo-Json -Depth 6
