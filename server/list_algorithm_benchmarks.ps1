param(
    [string]$OutDir = "",

    [switch]$LegacyScoringResearchOnly
)

$ErrorActionPreference = "Stop"

if (-not $LegacyScoringResearchOnly) {
    throw "Legacy benchmark history scoring is disabled for production. Pass -LegacyScoringResearchOnly only when deliberately inspecting old experiments; do not use these scores for rig decisions."
}

. (Join-Path $PSScriptRoot "aira_config.ps1")

$AiraConfig = Set-AiraProcessEnvironmentFromConfig
$ToolRoot = $AiraConfig.toolRoot
if ([string]::IsNullOrWhiteSpace($OutDir)) {
    $OutDir = Get-AiraOutDir
}

$HistoryDir = Join-Path $OutDir "algorithm_benchmarks"
$HistoryJson = Join-Path $OutDir "luxun_model_algorithm_benchmark_history.json"
$HistoryMd = Join-Path $OutDir "luxun_model_algorithm_benchmark_history.md"

$Runs = @()
if (Test-Path -LiteralPath $HistoryDir) {
    $ManifestFiles = Get-ChildItem -LiteralPath $HistoryDir -Recurse -Filter "run_manifest.json" -File
    foreach ($ManifestFile in $ManifestFiles) {
        $manifest = Get-Content -LiteralPath $ManifestFile.FullName -Raw | ConvertFrom-Json
        $recommended = @($manifest.results) | Where-Object { $_.algorithm -eq $manifest.recommendedAlgorithm } | Select-Object -First 1
        $Runs += [pscustomobject]@{
            runId = $manifest.runId
            generatedAt = $manifest.generatedAt
            configuredDefault = $manifest.configuredDefault
            legacySelectedAlgorithm = $manifest.recommendedAlgorithm
            legacyBipedScore = if ($null -ne $recommended) { $recommended.bipedScore } else { $null }
            legacyAverageDistance = if ($null -ne $recommended) { $recommended.bipedAverageDistance } else { $null }
            legacyFailures = if ($null -ne $recommended) { $recommended.bipedFailures } else { $null }
            legacyTemplateScore = if ($null -ne $recommended) { $recommended.templateScore } else { $null }
            legacyVisualScore = if ($null -ne $recommended) { $recommended.visualScore } else { $null }
            legacyStage01HandoffReady = if ($null -ne $recommended) { $recommended.stage01HandoffReady } else { $null }
            legacySkinSetupReady = if ($null -ne $recommended) { $recommended.skinSetupReady } else { $null }
            legacyQualityScore = if ($null -ne $recommended) { $recommended.qualityScore } else { $null }
            algorithmCount = @($manifest.algorithms).Count
            archiveDir = $manifest.archiveDir
            manifest = $ManifestFile.FullName
        }
    }
}

$Runs = @($Runs | Sort-Object generatedAt)
$Runs | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $HistoryJson -Encoding UTF8

$lines = @()
$lines += "# Luxun Legacy Algorithm Benchmark History"
$lines += ""
$lines += "> Legacy research only. These scores are disabled for production decisions; use the visual candidate generator plus Semantic Skin Review instead."
$lines += ""
$lines += "| Run ID | Generated At | Configured Default | Legacy Selected | Legacy Quality Score | Legacy Visual Score | Legacy Stage01 Handoff | Legacy Skin Setup | Legacy Biped Score | Avg Dist | Failures | Legacy Template Score | Algorithms |"
$lines += "| --- | --- | --- | --- | ---: | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: |"
foreach ($run in $Runs) {
    $lines += "| $($run.runId) | $($run.generatedAt) | $($run.configuredDefault) | $($run.legacySelectedAlgorithm) | $($run.legacyQualityScore) | $($run.legacyVisualScore) | $($run.legacyStage01HandoffReady) | $($run.legacySkinSetupReady) | $($run.legacyBipedScore) | $($run.legacyAverageDistance) | $($run.legacyFailures) | $($run.legacyTemplateScore) | $($run.algorithmCount) |"
}
$lines += ""
$lines += "## Manifests"
$lines += ""
foreach ($run in $Runs) {
    $lines += ("- ``{0}``: ``{1}``" -f $run.runId, $run.manifest)
}

$lines | Set-Content -LiteralPath $HistoryMd -Encoding UTF8

[pscustomobject]@{
    ok = $true
    runCount = $Runs.Count
    json = $HistoryJson
    markdown = $HistoryMd
    runs = $Runs
} | ConvertTo-Json -Depth 6
