$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "aira_config.ps1")

$Config = Set-AiraProcessEnvironmentFromConfig
$Root = $Config.toolRoot
$Python = $Config.python
$Server = Join-Path $PSScriptRoot "mcp_server.py"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Missing venv Python: $Python. Run: server\setup_local.ps1"
}

& $Python $Server
