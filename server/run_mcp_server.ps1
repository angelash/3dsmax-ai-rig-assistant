$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Server = Join-Path $PSScriptRoot "mcp_server.py"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Missing venv Python: $Python. Run: python -m venv F:\workspace\github\3dsmax-ai-rig-assistant\.venv"
}

& $Python $Server
