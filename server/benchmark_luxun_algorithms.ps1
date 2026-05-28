param(
    [string]$RunId = "",

    [string[]]$Algorithms = @(),

    [switch]$SkipArchive,

    [switch]$LegacyScoringResearchOnly
)

$ErrorActionPreference = "Stop"

throw "Legacy algorithm benchmark and quality scoring are fully disabled because they produced false confidence. Use batch_stage01_fbx.ps1 with tutorial_centerline_qbird as a visual candidate generator, then rely on Semantic Skin Review and MDC visual signoff. Use list_algorithm_benchmarks.ps1 -LegacyScoringResearchOnly only to read old archives."
