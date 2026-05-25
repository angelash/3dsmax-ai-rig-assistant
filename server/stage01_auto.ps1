$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "aira_config.ps1")

$Config = Set-AiraProcessEnvironmentFromConfig
$Root = $Config.toolRoot
$Python = $Config.python
$Cli = Join-Path $PSScriptRoot "direct_cli.py"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Missing venv Python: $Python. Run: server\setup_local.ps1"
}

& $Python $Cli stage01_auto_pipeline --host $Config.bridgeHost --port $Config.bridgePort
