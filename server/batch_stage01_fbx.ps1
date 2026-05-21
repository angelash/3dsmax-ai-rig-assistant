param(
    [Parameter(Mandatory = $true)]
    [string]$SourceFbx,

    [string]$AssetName = "",

    [ValidateSet("bbox_humanoid", "mesh_profile", "qbird_profile", "semantic_qbird", "visual_semantic_qbird", "tutorial_visual_qbird", "tutorial_centerline_qbird")]
    [string]$GuideAlgorithm = "tutorial_centerline_qbird",

    [string]$VisualSignoffJson = "",

    [switch]$SkipVlmReview,

    [string]$VlmReviewModel = "",

    [string]$OutDir = ""
)

$ErrorActionPreference = "Stop"

$RepoRoot = "F:\workspace\open-share"
$ToolRoot = "F:\workspace\github\3dsmax-ai-rig-assistant"
$BatchScript = Join-Path $ToolRoot "maxscript\batch_stage01_fbx_test.ms"
$VisualQcScript = Join-Path $ToolRoot "server\visual_qc.py"
$VisualReviewPackScript = Join-Path $ToolRoot "server\visual_review_pack.py"
$VlmReviewScript = Join-Path $ToolRoot "server\vlm_multiview_review.py"
$RigDetailReviewScript = Join-Path $ToolRoot "server\rig_detail_review.py"
$SkinPrepGateScript = Join-Path $ToolRoot "server\stage01_skin_prep_gate.py"
$OrganizeOutScript = Join-Path $ToolRoot "server\organize_out_dir.py"
$Python = Join-Path $ToolRoot ".venv\Scripts\python.exe"
$MaxBatch = "D:\Program files\Autodesk\3ds Max 2020\3dsmaxbatch.exe"
$AllowedVisualCandidateAlgorithm = "tutorial_centerline_qbird"

if ($GuideAlgorithm -ne $AllowedVisualCandidateAlgorithm) {
    throw "Guide algorithm '$GuideAlgorithm' is disabled. Legacy algorithm scoring is blocked; use '$AllowedVisualCandidateAlgorithm' only as a visual candidate generator, then rely on Semantic Skin Review and human visual signoff."
}

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

$oldFbxPath = [Environment]::GetEnvironmentVariable("AIRA_STAGE01_FBX_PATH", "Process")
$oldAssetName = [Environment]::GetEnvironmentVariable("AIRA_STAGE01_ASSET_NAME", "Process")
$oldGuideAlgo = [Environment]::GetEnvironmentVariable("AIRA_STAGE01_GUIDE_ALGO", "Process")
$oldTextureDir = [Environment]::GetEnvironmentVariable("AIRA_STAGE01_TEXTURE_DIR", "Process")

try {
    $env:AIRA_STAGE01_FBX_PATH = $WorkingFbx
    $env:AIRA_STAGE01_ASSET_NAME = $SafeAssetName
    $env:AIRA_STAGE01_GUIDE_ALGO = $GuideAlgorithm
    $env:AIRA_STAGE01_TEXTURE_DIR = $TextureSidecar

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
$GeneratedVlmSignoffJson = ""
$VlmReviewStatus = "not_requested"
$VlmReviewMessage = ""

if (-not [string]::IsNullOrWhiteSpace($VisualSignoffJson)) {
    if (-not (Test-Path -LiteralPath $VisualSignoffJson)) {
        throw "Visual signoff JSON not found: $VisualSignoffJson"
    }
    $EffectiveVisualSignoffJson = (Resolve-Path -LiteralPath $VisualSignoffJson).Path
    $VlmReviewStatus = "external_signoff_used"
    $VlmReviewMessage = "Using caller-provided visual signoff JSON."
}
elseif ($SkipVlmReview.IsPresent) {
    $VlmReviewStatus = "skipped"
    $VlmReviewMessage = "SkipVlmReview was set."
}
elseif (-not (Test-Path -LiteralPath $VlmReviewScript)) {
    $VlmReviewStatus = "skipped"
    $VlmReviewMessage = "VLM review script is missing."
}
elseif (-not (Test-Path -LiteralPath $OrganizedVisualReviewManifest)) {
    $VlmReviewStatus = "skipped"
    $VlmReviewMessage = "Visual review manifest is missing."
}
elseif ([string]::IsNullOrWhiteSpace($env:OPENAI_API_KEY)) {
    $VlmReviewStatus = "skipped"
    $VlmReviewMessage = "OPENAI_API_KEY is not set."
}
else {
    try {
        if (-not (Test-Path -LiteralPath $Python)) {
            $Python = "python"
        }
        $VisualReviewDir = Join-Path $RunDir "visual_review"
        New-Item -ItemType Directory -Force -Path $VisualReviewDir | Out-Null
        $GeneratedVlmSignoffJson = Join-Path $VisualReviewDir "$SafeAssetName`_semantic_visual_review_vlm.json"
        $VlmArgs = @(
            $VlmReviewScript,
            "--manifest-json", $OrganizedVisualReviewManifest,
            "--out-json", $GeneratedVlmSignoffJson
        )
        if (Test-Path -LiteralPath $OrganizedVisualReviewInput) {
            $VlmArgs += @("--review-input", $OrganizedVisualReviewInput)
        }
        if (Test-Path -LiteralPath $OrganizedVisualReviewSchema) {
            $VlmArgs += @("--schema-json", $OrganizedVisualReviewSchema)
        }
        if (-not [string]::IsNullOrWhiteSpace($VlmReviewModel)) {
            $VlmArgs += @("--model", $VlmReviewModel)
        }

        & $Python @VlmArgs | Out-Null
        if (Test-Path -LiteralPath $GeneratedVlmSignoffJson) {
            $EffectiveVisualSignoffJson = $GeneratedVlmSignoffJson
            $VlmReviewStatus = "completed"
            $VlmReviewMessage = "VLM visual signoff JSON generated."
        }
        else {
            $VlmReviewStatus = "failed"
            $VlmReviewMessage = "VLM review finished without writing signoff JSON."
        }
    }
    catch {
        $VlmReviewStatus = "failed"
        $VlmReviewMessage = $_.Exception.Message
    }
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

[pscustomobject]@{
    ok = (Test-Path -LiteralPath $OrganizedFitQcJson)
    sourceFbx = $SourceFbx
    workingFbx = $OrganizedWorkingFbx
    textureSidecar = $OrganizedTextureSidecar
    assetName = $SafeAssetName
    guideAlgorithm = $GuideAlgorithm
    organized = $Organized
    runDir = $RunDir
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
    vlmReviewJson = $GeneratedVlmSignoffJson
    vlmReviewStatus = $VlmReviewStatus
    vlmReviewMessage = $VlmReviewMessage
    stage01SkinPrepGateJson = $OrganizedSkinPrepGateJson
    stage01SkinPrepGateMarkdown = $OrganizedSkinPrepGateMarkdown
    rigAssetQcJson = $OrganizedRigAssetQcJson
    rigAssetQcMarkdown = $OrganizedRigAssetQcMarkdown
} | ConvertTo-Json -Depth 4
