param(
    [string]$RecommendationJson = "",

    [string]$OutDir = "",

    [string]$DestinationName = "default_recommended"
)

$ErrorActionPreference = "Stop"

throw "Promoting a score-ranked recommended algorithm is disabled. The pipeline now uses tutorial_centerline_qbird as a visual candidate generator plus Semantic Skin Review; do not promote legacy benchmark recommendations."
