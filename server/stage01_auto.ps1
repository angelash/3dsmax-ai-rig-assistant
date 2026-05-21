$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Cli = Join-Path $PSScriptRoot "direct_cli.py"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Missing venv Python: $Python. Run the setup in docs\mcp-setup.md first."
}

& $Python $Cli stage01_auto_pipeline
