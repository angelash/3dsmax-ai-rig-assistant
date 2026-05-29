param(
    [Parameter(Mandatory = $true)]
    [string]$SourceFbx,

    [string]$AssetName = "",

    [ValidateSet("bbox_humanoid", "mesh_profile", "qbird_profile", "semantic_qbird", "visual_semantic_qbird", "tutorial_visual_qbird", "tutorial_centerline_qbird")]
    [string]$GuideAlgorithm = "tutorial_centerline_qbird",

    [string]$VisualSignoffJson = "",

    [string]$MdcVisualCorrectionPlanJson = "",

    [int]$MdcVisualCorrectionPasses = 1,

    [int]$MaxFitIterations = 18,

    [string]$OutDir = "",

    [string]$MaxBatch = ""
)

$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "aira_config.ps1")

$AiraConfig = Set-AiraProcessEnvironmentFromConfig
$ToolRoot = $AiraConfig.toolRoot
$BatchScript = Join-Path $ToolRoot "maxscript\batch_stage01_fbx_test.ms"
$VisualQcScript = Join-Path $ToolRoot "server\visual_qc.py"
$VisualReviewPackScript = Join-Path $ToolRoot "server\visual_review_pack.py"
$VisualCorrectionPlanScript = Join-Path $ToolRoot "server\mdc_visual_correction_plan.py"
$VisualCorrectionDirectivesScript = Join-Path $ToolRoot "server\mdc_visual_correction_directives.py"
$RigDetailReviewScript = Join-Path $ToolRoot "server\rig_detail_review.py"
$SkinPrepGateScript = Join-Path $ToolRoot "server\stage01_skin_prep_gate.py"
$OrganizeOutScript = Join-Path $ToolRoot "server\organize_out_dir.py"
$NumberedLayoutScript = Join-Path $ToolRoot "server\stage01_numbered_layout.py"
$Python = Get-AiraPythonPath
$MaxBatch = Get-AiraMaxBatch $MaxBatch
$AllowedVisualCandidateAlgorithm = "tutorial_centerline_qbird"

if (-not (Test-Path -LiteralPath $MaxBatch -PathType Leaf)) {
    throw "3dsmaxbatch.exe not found: $MaxBatch. Run server\setup_local.ps1 or set AIRA_MAXBATCH."
}

if ($GuideAlgorithm -ne $AllowedVisualCandidateAlgorithm) {
    throw "Guide algorithm '$GuideAlgorithm' is disabled. Legacy algorithm scoring is blocked; use '$AllowedVisualCandidateAlgorithm' only as a visual candidate generator, then rely on Semantic Skin Review and MDC visual signoff."
}

if ($MdcVisualCorrectionPasses -lt 1) {
    $MdcVisualCorrectionPasses = 1
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

# Use an ASCII-only working path for 3ds Max 2020 importer stability.
$WorkingFbx = Join-Path $OutDir "$SafeAssetName.fbx"
Copy-Item -LiteralPath $SourceFbx -Destination $WorkingFbx -Force
$TextureSidecar = Copy-FbxTextureSidecar -SourceFbxPath $SourceFbx -WorkingFbxPath $WorkingFbx
$EffectiveMdcVisualCorrectionPlanJson = ""
$VisualCorrectionDirectivesTsv = ""
$VisualCorrectionDirectivesSummaryJson = ""
if (-not [string]::IsNullOrWhiteSpace($MdcVisualCorrectionPlanJson)) {
    if (-not (Test-Path -LiteralPath $MdcVisualCorrectionPlanJson -PathType Leaf)) {
        throw "MDC visual correction plan JSON not found: $MdcVisualCorrectionPlanJson"
    }
    if (-not (Test-Path -LiteralPath $VisualCorrectionDirectivesScript -PathType Leaf)) {
        throw "MDC visual correction directives script is missing: $VisualCorrectionDirectivesScript"
    }
    if (-not (Test-Path -LiteralPath $Python)) {
        $Python = "python"
    }
    $EffectiveMdcVisualCorrectionPlanJson = (Resolve-Path -LiteralPath $MdcVisualCorrectionPlanJson).Path
    $VisualCorrectionDirectivesTsv = Join-Path $OutDir "$SafeAssetName`_mdc_visual_correction_directives.tsv"
    $VisualCorrectionDirectivesSummaryJson = Join-Path $OutDir "$SafeAssetName`_mdc_visual_correction_directives.json"
    & $Python $VisualCorrectionDirectivesScript $EffectiveMdcVisualCorrectionPlanJson `
        --out-tsv $VisualCorrectionDirectivesTsv `
        --out-json $VisualCorrectionDirectivesSummaryJson | Out-Null
}

$oldFbxPath = [Environment]::GetEnvironmentVariable("AIRA_STAGE01_FBX_PATH", "Process")
$oldAssetName = [Environment]::GetEnvironmentVariable("AIRA_STAGE01_ASSET_NAME", "Process")
$oldGuideAlgo = [Environment]::GetEnvironmentVariable("AIRA_STAGE01_GUIDE_ALGO", "Process")
$oldTextureDir = [Environment]::GetEnvironmentVariable("AIRA_STAGE01_TEXTURE_DIR", "Process")
$oldMaxFitIterations = [Environment]::GetEnvironmentVariable("AIRA_STAGE01_MAX_FIT_ITERATIONS", "Process")
$oldCorrectionDirectives = [Environment]::GetEnvironmentVariable("AIRA_STAGE01_CORRECTION_DIRECTIVES_TSV", "Process")
$oldCorrectionPasses = [Environment]::GetEnvironmentVariable("AIRA_STAGE01_CORRECTION_PASSES", "Process")
$oldOutDir = [Environment]::GetEnvironmentVariable("AIRA_STAGE01_OUT_DIR", "Process")

try {
    $env:AIRA_STAGE01_FBX_PATH = $WorkingFbx
    $env:AIRA_STAGE01_ASSET_NAME = $SafeAssetName
    $env:AIRA_STAGE01_GUIDE_ALGO = $GuideAlgorithm
    $env:AIRA_STAGE01_TEXTURE_DIR = $TextureSidecar
    $env:AIRA_STAGE01_MAX_FIT_ITERATIONS = $MaxFitIterations
    $env:AIRA_STAGE01_CORRECTION_DIRECTIVES_TSV = $VisualCorrectionDirectivesTsv
    $env:AIRA_STAGE01_CORRECTION_PASSES = $MdcVisualCorrectionPasses
    $env:AIRA_STAGE01_OUT_DIR = $OutDir

    & $MaxBatch $BatchScript `
        -v 4 `
        -log (Join-Path $OutDir "$SafeAssetName`_stage01_3dsmaxbatch.log") `
        -listenerlog (Join-Path $OutDir "$SafeAssetName`_stage01_listener.log")
}
finally {
    if ($null -eq $oldFbxPath) {
        Remove-Item Env:AIRA_STAGE01_FBX_PATH -ErrorAction SilentlyContinue
    }
    else {
        $env:AIRA_STAGE01_FBX_PATH = $oldFbxPath
    }

    if ($null -eq $oldAssetName) {
        Remove-Item Env:AIRA_STAGE01_ASSET_NAME -ErrorAction SilentlyContinue
    }
    else {
        $env:AIRA_STAGE01_ASSET_NAME = $oldAssetName
    }

    if ($null -eq $oldGuideAlgo) {
        Remove-Item Env:AIRA_STAGE01_GUIDE_ALGO -ErrorAction SilentlyContinue
    }
    else {
        $env:AIRA_STAGE01_GUIDE_ALGO = $oldGuideAlgo
    }

    if ($null -eq $oldTextureDir) {
        Remove-Item Env:AIRA_STAGE01_TEXTURE_DIR -ErrorAction SilentlyContinue
    }
    else {
        $env:AIRA_STAGE01_TEXTURE_DIR = $oldTextureDir
    }

    if ($null -eq $oldMaxFitIterations) {
        Remove-Item Env:AIRA_STAGE01_MAX_FIT_ITERATIONS -ErrorAction SilentlyContinue
    }
    else {
        $env:AIRA_STAGE01_MAX_FIT_ITERATIONS = $oldMaxFitIterations
    }

    if ($null -eq $oldCorrectionDirectives) {
        Remove-Item Env:AIRA_STAGE01_CORRECTION_DIRECTIVES_TSV -ErrorAction SilentlyContinue
    }
    else {
        $env:AIRA_STAGE01_CORRECTION_DIRECTIVES_TSV = $oldCorrectionDirectives
    }

    if ($null -eq $oldCorrectionPasses) {
        Remove-Item Env:AIRA_STAGE01_CORRECTION_PASSES -ErrorAction SilentlyContinue
    }
    else {
        $env:AIRA_STAGE01_CORRECTION_PASSES = $oldCorrectionPasses
    }

    if ($null -eq $oldOutDir) {
        Remove-Item Env:AIRA_STAGE01_OUT_DIR -ErrorAction SilentlyContinue
    }
    else {
        $env:AIRA_STAGE01_OUT_DIR = $oldOutDir
    }
}

$VisualSnapshotJson = Join-Path $OutDir "$SafeAssetName`_visual_snapshot.json"
$VisualQcJson = Join-Path $OutDir "$SafeAssetName`_visual_qc.json"
$VisualQcMarkdown = Join-Path $OutDir "$SafeAssetName`_visual_qc.md"
$VisualScreenshotDir = Join-Path (Join-Path $OutDir "visual_screenshots") $SafeAssetName
$TexturedScreenshotDir = Join-Path (Join-Path $OutDir "textured_screenshots") $SafeAssetName
$WireBoneScreenshotDir = Join-Path (Join-Path $OutDir "wire_bone_screenshots") $SafeAssetName
$BodyProfileJson = Join-Path $OutDir "$SafeAssetName`_body_profile.json"
$FitQcJson = Join-Path $OutDir "$SafeAssetName`_stage01_fit_qc.json"
$RigDetailReviewJson = Join-Path $OutDir "$SafeAssetName`_rig_detail_review.json"
$RigDetailReviewMarkdown = Join-Path $OutDir "$SafeAssetName`_rig_detail_review.md"
$RigAssetQcJson = Join-Path $OutDir "$SafeAssetName`_stage01_rig_asset_qc.json"
$RigAssetQcMarkdown = Join-Path $OutDir "$SafeAssetName`_stage01_rig_asset_qc.md"
$SkinPrepGateJson = Join-Path $OutDir "$SafeAssetName`_stage01_skin_prep_gate.json"
$SkinPrepGateMarkdown = Join-Path $OutDir "$SafeAssetName`_stage01_skin_prep_gate.md"

if ((Test-Path -LiteralPath $VisualSnapshotJson) -and (Test-Path -LiteralPath $VisualQcScript)) {
    if (-not (Test-Path -LiteralPath $Python)) {
        $Python = "python"
    }
    & $Python $VisualQcScript $VisualSnapshotJson --asset-name $SafeAssetName --out-dir $OutDir | Out-Null
}

if ((Test-Path -LiteralPath $VisualSnapshotJson) -and (Test-Path -LiteralPath $RigDetailReviewScript)) {
    if (-not (Test-Path -LiteralPath $Python)) {
        $Python = "python"
    }
    & $Python $RigDetailReviewScript $VisualSnapshotJson --body-profile-json $BodyProfileJson --asset-name $SafeAssetName --out-dir $OutDir | Out-Null
}

if ((Test-Path -LiteralPath $SkinPrepGateScript) -and (Test-Path -LiteralPath $FitQcJson)) {
    if (-not (Test-Path -LiteralPath $Python)) {
        $Python = "python"
    }
    & $Python $SkinPrepGateScript `
        --asset-name $SafeAssetName `
        --body-profile-json $BodyProfileJson `
        --biped-fit-qc-json $FitQcJson `
        --visual-qc-json $VisualQcJson `
        --rig-detail-review-json $RigDetailReviewJson `
        --rig-asset-qc-json $RigAssetQcJson `
        --out-dir $OutDir | Out-Null
}

$Organized = $false
$OrganizeResult = $null
if (Test-Path -LiteralPath $OrganizeOutScript) {
    if (-not (Test-Path -LiteralPath $Python)) {
        $Python = "python"
    }
    $OrganizeRaw = & $Python $OrganizeOutScript --out-dir $OutDir
    $OrganizeJoined = ($OrganizeRaw | Out-String).Trim()
    if (-not [string]::IsNullOrWhiteSpace($OrganizeJoined)) {
        $OrganizeResult = $OrganizeJoined | ConvertFrom-Json
    }
    $Organized = $true
}

$RunDir = Join-Path (Join-Path $OutDir "runs") $SafeAssetName
if ($null -ne $OrganizeResult -and $null -ne $OrganizeResult.assetRuns) {
    $AssetRun = $OrganizeResult.assetRuns.PSObject.Properties[$SafeAssetName]
    if ($null -ne $AssetRun -and -not [string]::IsNullOrWhiteSpace($AssetRun.Value.runDir)) {
        $RunDir = $AssetRun.Value.runDir
    }
}

$RunSceneDir = Join-Path $RunDir "scene"
$RunDataDir = Join-Path $RunDir "data"
New-Item -ItemType Directory -Force -Path $RunSceneDir | Out-Null
New-Item -ItemType Directory -Force -Path $RunDataDir | Out-Null

function Move-AiraGeneratedFileToRunScene {
    param(
        [string]$PathValue
    )

    if ([string]::IsNullOrWhiteSpace($PathValue) -or -not (Test-Path -LiteralPath $PathValue -PathType Leaf)) {
        return $PathValue
    }

    $Target = Join-Path $RunSceneDir ([System.IO.Path]::GetFileName($PathValue))
    $SourceFull = [System.IO.Path]::GetFullPath($PathValue)
    $TargetFull = [System.IO.Path]::GetFullPath($Target)
    if ($SourceFull -ne $TargetFull) {
        Move-Item -LiteralPath $PathValue -Destination $Target -Force
    }
    return $Target
}

function Move-AiraGeneratedFileToRunData {
    param(
        [string]$PathValue
    )

    if ([string]::IsNullOrWhiteSpace($PathValue)) {
        return $PathValue
    }

    if (-not (Test-Path -LiteralPath $PathValue -PathType Leaf)) {
        $MiscCandidate = Join-Path (Join-Path $OutDir "misc") ([System.IO.Path]::GetFileName($PathValue))
        if (Test-Path -LiteralPath $MiscCandidate -PathType Leaf) {
            $PathValue = $MiscCandidate
        }
        else {
            return $PathValue
        }
    }

    $Target = Join-Path $RunDataDir ([System.IO.Path]::GetFileName($PathValue))
    $SourceFull = [System.IO.Path]::GetFullPath($PathValue)
    $TargetFull = [System.IO.Path]::GetFullPath($Target)
    if ($SourceFull -ne $TargetFull) {
        Move-Item -LiteralPath $PathValue -Destination $Target -Force
    }
    return $Target
}

function Move-AiraGeneratedDirectoryToRunScene {
    param(
        [string]$PathValue
    )

    if ([string]::IsNullOrWhiteSpace($PathValue) -or -not (Test-Path -LiteralPath $PathValue -PathType Container)) {
        return $PathValue
    }

    $Target = Join-Path $RunSceneDir ([System.IO.Path]::GetFileName($PathValue))
    $SourceFull = [System.IO.Path]::GetFullPath($PathValue)
    $TargetFull = [System.IO.Path]::GetFullPath($Target)
    if ($SourceFull -eq $TargetFull) {
        return $Target
    }

    if (-not (Test-Path -LiteralPath $Target -PathType Container)) {
        Move-Item -LiteralPath $PathValue -Destination $Target -Force
    }
    else {
        Get-ChildItem -LiteralPath $PathValue -Force | ForEach-Object {
            Move-Item -LiteralPath $_.FullName -Destination $Target -Force
        }
        Remove-Item -LiteralPath $PathValue -Force
    }
    return $Target
}

$MiscWorkingFbx = Join-Path (Join-Path $OutDir "misc") "$SafeAssetName.fbx"
if ((-not (Test-Path -LiteralPath $WorkingFbx -PathType Leaf)) -and (Test-Path -LiteralPath $MiscWorkingFbx -PathType Leaf)) {
    $WorkingFbx = $MiscWorkingFbx
}
$WorkingFbx = Move-AiraGeneratedFileToRunScene $WorkingFbx
$TextureSidecar = Move-AiraGeneratedDirectoryToRunScene $TextureSidecar
$VisualCorrectionDirectivesTsv = Move-AiraGeneratedFileToRunData $VisualCorrectionDirectivesTsv
$VisualCorrectionDirectivesSummaryJson = Move-AiraGeneratedFileToRunData $VisualCorrectionDirectivesSummaryJson

function Resolve-AiraOutputPath {
    param(
        [string]$SubDir,
        [string]$FileName,
        [string]$FallbackPath
    )

    $Candidate = Join-Path (Join-Path $RunDir $SubDir) $FileName
    if (Test-Path -LiteralPath $Candidate) {
        return $Candidate
    }
    return $FallbackPath
}

$OrganizedWorkingFbx = Resolve-AiraOutputPath "scene" "$SafeAssetName.fbx" $WorkingFbx
$OrganizedTextureSidecar = Join-Path (Join-Path $RunDir "scene") "$SafeAssetName.fbm"
if (-not (Test-Path -LiteralPath $OrganizedTextureSidecar)) {
    $OrganizedTextureSidecar = $TextureSidecar
}
$OrganizedScene = Resolve-AiraOutputPath "scene" "$SafeAssetName`_stage01_rig_scene.max" (Join-Path $OutDir "$SafeAssetName`_stage01_rig_scene.max")
$OrganizedSummary = Resolve-AiraOutputPath "reports" "$SafeAssetName`_stage01_batch_summary.md" (Join-Path $OutDir "$SafeAssetName`_stage01_batch_summary.md")
$OrganizedBodyProfileJson = Resolve-AiraOutputPath "data" "$SafeAssetName`_body_profile.json" $BodyProfileJson
$OrganizedBodyProfileMarkdown = Resolve-AiraOutputPath "reports" "$SafeAssetName`_body_profile.md" (Join-Path $OutDir "$SafeAssetName`_body_profile.md")
$OrganizedFitQcJson = Resolve-AiraOutputPath "data" "$SafeAssetName`_stage01_fit_qc.json" $FitQcJson
$OrganizedFitQcMarkdown = Resolve-AiraOutputPath "reports" "$SafeAssetName`_stage01_fit_qc.md" (Join-Path $OutDir "$SafeAssetName`_stage01_fit_qc.md")
$OrganizedVisualSnapshotJson = Resolve-AiraOutputPath "data" "$SafeAssetName`_visual_snapshot.json" $VisualSnapshotJson
$OrganizedVisualQcJson = Resolve-AiraOutputPath "data" "$SafeAssetName`_visual_qc.json" $VisualQcJson
$OrganizedVisualQcMarkdown = Resolve-AiraOutputPath "reports" "$SafeAssetName`_visual_qc.md" $VisualQcMarkdown
$OrganizedRigDetailReviewJson = Resolve-AiraOutputPath "data" "$SafeAssetName`_rig_detail_review.json" $RigDetailReviewJson
$OrganizedRigDetailReviewMarkdown = Resolve-AiraOutputPath "reports" "$SafeAssetName`_rig_detail_review.md" $RigDetailReviewMarkdown
$OrganizedSkinPrepGateJson = Resolve-AiraOutputPath "data" "$SafeAssetName`_stage01_skin_prep_gate.json" $SkinPrepGateJson
$OrganizedSkinPrepGateMarkdown = Resolve-AiraOutputPath "reports" "$SafeAssetName`_stage01_skin_prep_gate.md" $SkinPrepGateMarkdown
$OrganizedRigAssetQcJson = Resolve-AiraOutputPath "data" "$SafeAssetName`_stage01_rig_asset_qc.json" $RigAssetQcJson
$OrganizedRigAssetQcMarkdown = Resolve-AiraOutputPath "reports" "$SafeAssetName`_stage01_rig_asset_qc.md" $RigAssetQcMarkdown

if ((Test-Path -LiteralPath $VisualReviewPackScript) -and (Test-Path -LiteralPath $OrganizedVisualSnapshotJson)) {
    if (-not (Test-Path -LiteralPath $Python)) {
        $Python = "python"
    }
    & $Python $VisualReviewPackScript $OrganizedVisualSnapshotJson `
        --asset-name $SafeAssetName `
        --out-dir $RunDir `
        --visual-qc-json $OrganizedVisualQcJson `
        --rig-detail-review-json $OrganizedRigDetailReviewJson `
        --skin-prep-gate-json $OrganizedSkinPrepGateJson `
        --body-profile-json $OrganizedBodyProfileJson | Out-Null

    if (Test-Path -LiteralPath $OrganizeOutScript) {
        $OrganizeRaw = & $Python $OrganizeOutScript --out-dir $OutDir
        $OrganizeJoined = ($OrganizeRaw | Out-String).Trim()
        if (-not [string]::IsNullOrWhiteSpace($OrganizeJoined)) {
            $OrganizeResult = $OrganizeJoined | ConvertFrom-Json
        }
    }
}

$OrganizedVisualReviewManifest = Resolve-AiraOutputPath "visual_review" "$SafeAssetName`_visual_evidence_manifest.json" (Join-Path (Join-Path $RunDir "visual_review") "$SafeAssetName`_visual_evidence_manifest.json")
$OrganizedVisualReviewInput = Resolve-AiraOutputPath "visual_review" "review_input.md" (Join-Path (Join-Path $RunDir "visual_review") "review_input.md")
$OrganizedVisualReviewSchema = Resolve-AiraOutputPath "visual_review" "review_schema.json" (Join-Path (Join-Path $RunDir "visual_review") "review_schema.json")
$OrganizedSliceAnalysisJson = Join-Path (Join-Path (Join-Path $RunDir "visual_review") "slices") "slice_analysis.json"
$OrganizedVisualScreenshotDir = Join-Path $RunDir "screenshots"
if (-not (Test-Path -LiteralPath $OrganizedVisualScreenshotDir)) {
    $OrganizedVisualScreenshotDir = $VisualScreenshotDir
}
$OrganizedTexturedScreenshotDir = Join-Path $RunDir "textured_screenshots"
if (-not (Test-Path -LiteralPath $OrganizedTexturedScreenshotDir)) {
    $OrganizedTexturedScreenshotDir = $TexturedScreenshotDir
}
$OrganizedWireBoneScreenshotDir = Join-Path $RunDir "wire_bone_screenshots"
if (-not (Test-Path -LiteralPath $OrganizedWireBoneScreenshotDir)) {
    $OrganizedWireBoneScreenshotDir = $WireBoneScreenshotDir
}

$EffectiveVisualSignoffJson = ""
$VisualReviewStatus = "awaiting_local_signoff"
$VisualReviewMessage = "Visual evidence pack generated; provide -VisualSignoffJson after MDC local-agent image review."

if (-not [string]::IsNullOrWhiteSpace($VisualSignoffJson)) {
    if (-not (Test-Path -LiteralPath $VisualSignoffJson)) {
        throw "Visual signoff JSON not found: $VisualSignoffJson"
    }
    $EffectiveVisualSignoffJson = (Resolve-Path -LiteralPath $VisualSignoffJson).Path
    $VisualReviewStatus = "local_signoff_used"
    $VisualReviewMessage = "Using caller-provided local visual signoff JSON."
}
elseif (-not (Test-Path -LiteralPath $OrganizedVisualReviewManifest)) {
    $VisualReviewStatus = "evidence_missing"
    $VisualReviewMessage = "Visual review manifest is missing; no API fallback is available."
}

if ((Test-Path -LiteralPath $SkinPrepGateScript) -and (Test-Path -LiteralPath $OrganizedFitQcJson)) {
    if (-not (Test-Path -LiteralPath $Python)) {
        $Python = "python"
    }
    $FinalGateDataDir = Join-Path $RunDir "data"
    $FinalGateReportDir = Join-Path $RunDir "reports"
    New-Item -ItemType Directory -Force -Path $FinalGateDataDir | Out-Null
    New-Item -ItemType Directory -Force -Path $FinalGateReportDir | Out-Null

    $SkinGateArgs = @(
        $SkinPrepGateScript,
        "--asset-name", $SafeAssetName,
        "--body-profile-json", $OrganizedBodyProfileJson,
        "--biped-fit-qc-json", $OrganizedFitQcJson,
        "--visual-qc-json", $OrganizedVisualQcJson,
        "--rig-detail-review-json", $OrganizedRigDetailReviewJson,
        "--rig-asset-qc-json", $OrganizedRigAssetQcJson,
        "--slice-analysis-json", $OrganizedSliceAnalysisJson,
        "--out-dir", $FinalGateDataDir,
        "--md-out-dir", $FinalGateReportDir
    )
    if (-not [string]::IsNullOrWhiteSpace($EffectiveVisualSignoffJson)) {
        $SkinGateArgs += @("--visual-signoff-json", $EffectiveVisualSignoffJson)
    }

    & $Python @SkinGateArgs | Out-Null
    $OrganizedSkinPrepGateJson = Resolve-AiraOutputPath "data" "$SafeAssetName`_stage01_skin_prep_gate.json" $SkinPrepGateJson
    $OrganizedSkinPrepGateMarkdown = Resolve-AiraOutputPath "reports" "$SafeAssetName`_stage01_skin_prep_gate.md" $SkinPrepGateMarkdown
}

$OrganizedVisualCorrectionPlanJson = ""
$OrganizedVisualCorrectionPlanMarkdown = ""
if (
    (Test-Path -LiteralPath $VisualCorrectionPlanScript) -and
    (Test-Path -LiteralPath $OrganizedVisualSnapshotJson) -and
    (Test-Path -LiteralPath $OrganizedVisualQcJson) -and
    (-not [string]::IsNullOrWhiteSpace($EffectiveVisualSignoffJson))
) {
    if (-not (Test-Path -LiteralPath $Python)) {
        $Python = "python"
    }
    $CorrectionDataDir = Join-Path $RunDir "data"
    $CorrectionReportDir = Join-Path $RunDir "reports"
    New-Item -ItemType Directory -Force -Path $CorrectionDataDir | Out-Null
    New-Item -ItemType Directory -Force -Path $CorrectionReportDir | Out-Null

    $CorrectionArgs = @(
        $VisualCorrectionPlanScript,
        $OrganizedVisualSnapshotJson,
        "--asset-name", $SafeAssetName,
        "--visual-qc-json", $OrganizedVisualQcJson,
        "--visual-signoff-json", $EffectiveVisualSignoffJson,
        "--slice-analysis-json", $OrganizedSliceAnalysisJson,
        "--out-dir", $CorrectionDataDir,
        "--md-out-dir", $CorrectionReportDir
    )
    & $Python @CorrectionArgs | Out-Null
    $OrganizedVisualCorrectionPlanJson = Resolve-AiraOutputPath "data" "$SafeAssetName`_mdc_visual_correction_plan.json" (Join-Path $CorrectionDataDir "$SafeAssetName`_mdc_visual_correction_plan.json")
    $OrganizedVisualCorrectionPlanMarkdown = Resolve-AiraOutputPath "reports" "$SafeAssetName`_mdc_visual_correction_plan.md" (Join-Path $CorrectionReportDir "$SafeAssetName`_mdc_visual_correction_plan.md")
}

$NumberedLayout = $null
$LayoutVersion = "legacy_unordered"
if ((Test-Path -LiteralPath $NumberedLayoutScript) -and (Test-Path -LiteralPath $RunDir)) {
    if (-not (Test-Path -LiteralPath $Python)) {
        $Python = "python"
    }
    $LayoutRaw = & $Python $NumberedLayoutScript --run-dir $RunDir --asset-name $SafeAssetName
    $LayoutJoined = ($LayoutRaw | Out-String).Trim()
    if (-not [string]::IsNullOrWhiteSpace($LayoutJoined)) {
        $NumberedLayout = $LayoutJoined | ConvertFrom-Json
        $LayoutVersion = $NumberedLayout.layoutVersion
    }
}

function Convert-AiraNumberedLayoutPath {
    param(
        [string]$PathValue
    )

    if ([string]::IsNullOrWhiteSpace($PathValue)) {
        return $PathValue
    }
    if ($null -eq $NumberedLayout -or $null -eq $NumberedLayout.legacyToNumbered) {
        return $PathValue
    }

    foreach ($prop in $NumberedLayout.legacyToNumbered.PSObject.Properties) {
        $LegacyDir = Join-Path $RunDir $prop.Name
        $NumberedDir = [string]$prop.Value
        if ($PathValue.StartsWith($LegacyDir, [System.StringComparison]::OrdinalIgnoreCase)) {
            return ($NumberedDir + $PathValue.Substring($LegacyDir.Length))
        }
    }
    return $PathValue
}

$OrganizedWorkingFbx = Convert-AiraNumberedLayoutPath $OrganizedWorkingFbx
$OrganizedTextureSidecar = Convert-AiraNumberedLayoutPath $OrganizedTextureSidecar
$OrganizedScene = Convert-AiraNumberedLayoutPath $OrganizedScene
$OrganizedSummary = Convert-AiraNumberedLayoutPath $OrganizedSummary
$OrganizedBodyProfileJson = Convert-AiraNumberedLayoutPath $OrganizedBodyProfileJson
$OrganizedBodyProfileMarkdown = Convert-AiraNumberedLayoutPath $OrganizedBodyProfileMarkdown
$OrganizedFitQcJson = Convert-AiraNumberedLayoutPath $OrganizedFitQcJson
$OrganizedFitQcMarkdown = Convert-AiraNumberedLayoutPath $OrganizedFitQcMarkdown
$OrganizedVisualSnapshotJson = Convert-AiraNumberedLayoutPath $OrganizedVisualSnapshotJson
$OrganizedVisualQcJson = Convert-AiraNumberedLayoutPath $OrganizedVisualQcJson
$OrganizedVisualQcMarkdown = Convert-AiraNumberedLayoutPath $OrganizedVisualQcMarkdown
$OrganizedVisualScreenshotDir = Convert-AiraNumberedLayoutPath $OrganizedVisualScreenshotDir
$OrganizedTexturedScreenshotDir = Convert-AiraNumberedLayoutPath $OrganizedTexturedScreenshotDir
$OrganizedWireBoneScreenshotDir = Convert-AiraNumberedLayoutPath $OrganizedWireBoneScreenshotDir
$OrganizedRigDetailReviewJson = Convert-AiraNumberedLayoutPath $OrganizedRigDetailReviewJson
$OrganizedRigDetailReviewMarkdown = Convert-AiraNumberedLayoutPath $OrganizedRigDetailReviewMarkdown
$OrganizedVisualReviewManifest = Convert-AiraNumberedLayoutPath $OrganizedVisualReviewManifest
$OrganizedVisualReviewInput = Convert-AiraNumberedLayoutPath $OrganizedVisualReviewInput
$OrganizedVisualReviewSchema = Convert-AiraNumberedLayoutPath $OrganizedVisualReviewSchema
$EffectiveVisualSignoffJson = Convert-AiraNumberedLayoutPath $EffectiveVisualSignoffJson
$EffectiveMdcVisualCorrectionPlanJson = Convert-AiraNumberedLayoutPath $EffectiveMdcVisualCorrectionPlanJson
$VisualCorrectionDirectivesTsv = Convert-AiraNumberedLayoutPath $VisualCorrectionDirectivesTsv
$VisualCorrectionDirectivesSummaryJson = Convert-AiraNumberedLayoutPath $VisualCorrectionDirectivesSummaryJson
$OrganizedSkinPrepGateJson = Convert-AiraNumberedLayoutPath $OrganizedSkinPrepGateJson
$OrganizedSkinPrepGateMarkdown = Convert-AiraNumberedLayoutPath $OrganizedSkinPrepGateMarkdown
$OrganizedVisualCorrectionPlanJson = Convert-AiraNumberedLayoutPath $OrganizedVisualCorrectionPlanJson
$OrganizedVisualCorrectionPlanMarkdown = Convert-AiraNumberedLayoutPath $OrganizedVisualCorrectionPlanMarkdown
$OrganizedRigAssetQcJson = Convert-AiraNumberedLayoutPath $OrganizedRigAssetQcJson
$OrganizedRigAssetQcMarkdown = Convert-AiraNumberedLayoutPath $OrganizedRigAssetQcMarkdown

[pscustomobject]@{
    ok = (Test-Path -LiteralPath $OrganizedFitQcJson)
    sourceFbx = $SourceFbx
    workingFbx = $OrganizedWorkingFbx
    textureSidecar = $OrganizedTextureSidecar
    assetName = $SafeAssetName
    guideAlgorithm = $GuideAlgorithm
    maxFitIterations = $MaxFitIterations
    organized = $Organized
    layoutVersion = $LayoutVersion
    runDir = $RunDir
    layoutManifest = Join-Path $RunDir "layout_manifest.json"
    scene = $OrganizedScene
    summary = $OrganizedSummary
    bodyProfileJson = $OrganizedBodyProfileJson
    bodyProfileMarkdown = $OrganizedBodyProfileMarkdown
    fitQcJson = $OrganizedFitQcJson
    fitQcMarkdown = $OrganizedFitQcMarkdown
    visualSnapshotJson = $OrganizedVisualSnapshotJson
    visualQcJson = $OrganizedVisualQcJson
    visualQcMarkdown = $OrganizedVisualQcMarkdown
    visualScreenshotDir = $OrganizedVisualScreenshotDir
    texturedScreenshotDir = $OrganizedTexturedScreenshotDir
    wireBoneScreenshotDir = $OrganizedWireBoneScreenshotDir
    rigDetailReviewJson = $OrganizedRigDetailReviewJson
    rigDetailReviewMarkdown = $OrganizedRigDetailReviewMarkdown
    visualReviewManifest = $OrganizedVisualReviewManifest
    visualReviewInput = $OrganizedVisualReviewInput
    visualReviewSchema = $OrganizedVisualReviewSchema
    visualSignoffJson = $EffectiveVisualSignoffJson
    visualReviewStatus = $VisualReviewStatus
    visualReviewMessage = $VisualReviewMessage
    mdcVisualCorrectionPlanJson = $OrganizedVisualCorrectionPlanJson
    mdcVisualCorrectionPlanMarkdown = $OrganizedVisualCorrectionPlanMarkdown
    mdcVisualCorrectionInputPlanJson = $EffectiveMdcVisualCorrectionPlanJson
    mdcVisualCorrectionPasses = $MdcVisualCorrectionPasses
    mdcVisualCorrectionDirectivesTsv = $VisualCorrectionDirectivesTsv
    mdcVisualCorrectionDirectivesSummaryJson = $VisualCorrectionDirectivesSummaryJson
    stage01SkinPrepGateJson = $OrganizedSkinPrepGateJson
    stage01SkinPrepGateMarkdown = $OrganizedSkinPrepGateMarkdown
    rigAssetQcJson = $OrganizedRigAssetQcJson
    rigAssetQcMarkdown = $OrganizedRigAssetQcMarkdown
} | ConvertTo-Json -Depth 4
