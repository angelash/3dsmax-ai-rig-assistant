param(
    [string]$RegistryPath = "",

    [string]$RecommendationJson = "",

    [string]$OutDir = "",

    [switch]$Apply
)

$ErrorActionPreference = "Stop"

throw "Checking score-ranked algorithm recommendations is disabled. The default registry is no longer maintained by benchmark quality scores; use tutorial_centerline_qbird as a visual candidate generator plus Semantic Skin Review."
