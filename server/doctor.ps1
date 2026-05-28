param(
    [switch]$Json,
    [switch]$CheckBridge
)

$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "aira_config.ps1")

$Config = Set-AiraProcessEnvironmentFromConfig
$Checks = @()

function Add-AiraCheck {
    param(
        [string]$Name,
        [string]$Status,
        [string]$Message,
        [string]$Path = ""
    )

    $script:Checks += [pscustomobject]@{
        name = $Name
        status = $Status
        message = $Message
        path = $Path
    }
}

function Test-AiraFile {
    param(
        [string]$Name,
        [string]$Path,
        [string]$MissingMessage
    )

    if (Test-Path -LiteralPath $Path -PathType Leaf) {
        Add-AiraCheck $Name "ok" "Found." $Path
    }
    else {
        Add-AiraCheck $Name "error" $MissingMessage $Path
    }
}

function Test-AiraDirectory {
    param(
        [string]$Name,
        [string]$Path,
        [string]$MissingMessage
    )

    if (Test-Path -LiteralPath $Path -PathType Container) {
        Add-AiraCheck $Name "ok" "Found." $Path
    }
    else {
        Add-AiraCheck $Name "warning" $MissingMessage $Path
    }
}

$LocalConfigPath = Get-AiraLocalConfigPath
if (Test-Path -LiteralPath $LocalConfigPath -PathType Leaf) {
    Add-AiraCheck "local_config" "ok" "Local config is present." $LocalConfigPath
}
else {
    Add-AiraCheck "local_config" "warning" "Run server\setup_local.ps1 to generate per-machine config." $LocalConfigPath
}

Test-AiraDirectory "tool_root" $Config.toolRoot "Tool root does not exist."
Test-AiraDirectory "source_root" $Config.sourceRoot "Source assets directory is missing; create it or update config/local.json."
Test-AiraDirectory "out_dir" $Config.outDir "Output directory is missing; setup_local.ps1 will create it."
Test-AiraDirectory "report_root" $Config.reportRoot "Report directory is missing; setup_local.ps1 will create it."

Test-AiraFile "python" $Config.python "Configured venv Python is missing."
Test-AiraFile "3dsmaxbatch" $Config.maxBatch "3dsmaxbatch.exe was not found. Set maxBatch in config/local.json or AIRA_MAXBATCH."
Test-AiraFile "mcp_server" (Join-Path $Config.toolRoot "server\mcp_server.py") "MCP server script is missing."
Test-AiraFile "bridge_script" (Join-Path $Config.toolRoot "maxscript\aira_mcp_bridge.ms") "3ds Max bridge script is missing."
Test-AiraFile "stage01_script" (Join-Path $Config.toolRoot "maxscript\aira_stage01_biped.ms") "Stage01 MaxScript is missing."
Test-AiraFile "stage02_script" (Join-Path $Config.toolRoot "maxscript\aira_stage02_skin.ms") "Stage02 MaxScript is missing."
Test-AiraFile "asset_qc_script" (Join-Path $Config.toolRoot "maxscript\aira_asset_qc.ms") "Asset QC MaxScript is missing."
Test-AiraFile "visual_correction_plan_script" (Join-Path $Config.toolRoot "server\mdc_visual_correction_plan.py") "MDC visual correction planner is missing."

$McpLocalConfig = Join-Path $Config.toolRoot "config\mcp.local.json"
if (Test-Path -LiteralPath $McpLocalConfig -PathType Leaf) {
    Add-AiraCheck "mcp_local_config" "ok" "Generated MCP config is present." $McpLocalConfig
}
else {
    Add-AiraCheck "mcp_local_config" "warning" "Run server\setup_local.ps1 to generate config\mcp.local.json." $McpLocalConfig
}

if (Test-Path -LiteralPath $Config.python -PathType Leaf) {
    $ImportExitCode = 0
    try {
        $ImportOutput = & $Config.python -c "import mcp; print('ok')" 2>&1
        $ImportExitCode = $LASTEXITCODE
    }
    catch {
        $ImportOutput = $_.Exception.Message
        $ImportExitCode = 1
    }
    if ($ImportExitCode -eq 0) {
        Add-AiraCheck "python_requirements" "ok" "Required MCP Python package imports successfully." $Config.python
    }
    else {
        Add-AiraCheck "python_requirements" "error" "Python requirements are missing or broken: $ImportOutput" $Config.python
    }
}

Add-AiraCheck "local_visual_signoff" "ok" "Stage01 uses local evidence packs and caller-provided visual signoff JSON; no API key is required." "visual_review/review_schema.json"

if ($CheckBridge.IsPresent -and (Test-Path -LiteralPath $Config.python -PathType Leaf)) {
    $Cli = Join-Path $Config.toolRoot "server\direct_cli.py"
    $BridgeExitCode = 0
    try {
        $BridgeOutput = & $Config.python $Cli ping --host $Config.bridgeHost --port $Config.bridgePort --timeout 3 2>&1
        $BridgeExitCode = $LASTEXITCODE
    }
    catch {
        $BridgeOutput = $_.Exception.Message
        $BridgeExitCode = 1
    }
    if ($BridgeExitCode -eq 0) {
        Add-AiraCheck "3dsmax_bridge" "ok" "Bridge responded to ping." "$($Config.bridgeHost):$($Config.bridgePort)"
    }
    else {
        Add-AiraCheck "3dsmax_bridge" "warning" "Bridge did not respond. Run maxscript\aira_mcp_bridge.ms inside 3ds Max first. $BridgeOutput" "$($Config.bridgeHost):$($Config.bridgePort)"
    }
}

$HasErrors = @($Checks | Where-Object { $_.status -eq "error" }).Count -gt 0
$Result = [pscustomobject]@{
    ok = -not $HasErrors
    config = $Config
    checks = $Checks
}

if ($Json.IsPresent) {
    $Result | ConvertTo-Json -Depth 8
}
else {
    $Checks | Format-Table -AutoSize
    if ($HasErrors) {
        Write-Host "AIRA doctor found blocking errors." -ForegroundColor Red
    }
    else {
        Write-Host "AIRA doctor passed without blocking errors." -ForegroundColor Green
    }
}

if ($HasErrors) {
    exit 1
}
exit 0
