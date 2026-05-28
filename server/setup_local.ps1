param(
    [string]$MaxBatch = "",
    [string]$SourceRoot = "",
    [string]$OutDir = "",
    [string]$ReportRoot = "",
    [string]$Python = "",
    [switch]$SkipVenv,
    [switch]$SkipInstall,
    [switch]$InstallGeometry,
    [switch]$Overwrite
)

$ErrorActionPreference = "Stop"

$env:AIRA_TOOL_ROOT = [System.IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
. (Join-Path $PSScriptRoot "aira_config.ps1")

$ToolRoot = Get-AiraToolRoot
$ConfigDir = Join-Path $ToolRoot "config"
$ConfigPath = Join-Path $ConfigDir "local.json"
$McpConfigPath = Join-Path $ConfigDir "mcp.local.json"

if ((Test-Path -LiteralPath $ConfigPath) -and -not $Overwrite.IsPresent) {
    throw "Local config already exists: $ConfigPath. Pass -Overwrite to regenerate it."
}

if ([string]::IsNullOrWhiteSpace($SourceRoot)) { $SourceRoot = Join-Path $ToolRoot "source" } else { $SourceRoot = ConvertTo-AiraAbsolutePath $SourceRoot }
if ([string]::IsNullOrWhiteSpace($OutDir)) { $OutDir = Join-Path $ToolRoot "out" } else { $OutDir = ConvertTo-AiraAbsolutePath $OutDir }
if ([string]::IsNullOrWhiteSpace($ReportRoot)) { $ReportRoot = Join-Path $ToolRoot "report" } else { $ReportRoot = ConvertTo-AiraAbsolutePath $ReportRoot }
if ([string]::IsNullOrWhiteSpace($Python)) { $Python = Join-Path $ToolRoot ".venv\Scripts\python.exe" } else { $Python = ConvertTo-AiraAbsolutePath $Python }
if ([string]::IsNullOrWhiteSpace($MaxBatch)) { $MaxBatch = Find-AiraMaxBatch } else { $MaxBatch = ConvertTo-AiraAbsolutePath $MaxBatch }

New-Item -ItemType Directory -Force -Path $ConfigDir | Out-Null
New-Item -ItemType Directory -Force -Path $SourceRoot | Out-Null
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
New-Item -ItemType Directory -Force -Path $ReportRoot | Out-Null

$LocalConfig = [ordered]@{
    toolRoot = $ToolRoot
    sourceRoot = $SourceRoot
    outDir = $OutDir
    reportRoot = $ReportRoot
    python = $Python
    maxBatch = $MaxBatch
    bridge = [ordered]@{
        host = "127.0.0.1"
        port = 37820
    }
    mcp = [ordered]@{
        serverName = "3dsmax-ai-rig-assistant"
        configOut = $McpConfigPath
    }
}

$LocalConfig | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $ConfigPath -Encoding UTF8

if (-not $SkipVenv.IsPresent -and -not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    $VenvDir = Split-Path -Parent (Split-Path -Parent $Python)
    & python -m venv $VenvDir
}

if (-not $SkipInstall.IsPresent -and (Test-Path -LiteralPath $Python -PathType Leaf)) {
    & $Python -m pip install -r (Join-Path $ToolRoot "requirements.txt")
    if ($InstallGeometry.IsPresent) {
        & $Python -m pip install -r (Join-Path $ToolRoot "requirements-geometry.txt")
    }
}

$McpEnv = [ordered]@{
    AIRA_TOOL_ROOT = $ToolRoot
    AIRA_SOURCE_ROOT = $SourceRoot
    AIRA_OUT_DIR = $OutDir
    AIRA_REPORT_ROOT = $ReportRoot
    AIRA_MAXBATCH = $MaxBatch
    AIRA_MCP_HOST = "127.0.0.1"
    AIRA_MCP_PORT = "37820"
}

$McpConfig = [ordered]@{
    mcpServers = [ordered]@{
        "3dsmax-ai-rig-assistant" = [ordered]@{
            command = $Python
            args = @((Join-Path $ToolRoot "server\mcp_server.py"))
            env = $McpEnv
        }
    }
}
$McpConfig | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $McpConfigPath -Encoding UTF8

& (Join-Path $PSScriptRoot "doctor.ps1") -Json
