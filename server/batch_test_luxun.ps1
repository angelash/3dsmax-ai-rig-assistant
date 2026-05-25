$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "aira_config.ps1")

$ToolRoot = Get-AiraToolRoot
$SourceFbx = Join-Path $ToolRoot "source\luxun_model\陆逊模型.fbx"
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

& (Join-Path $ScriptRoot "batch_stage01_fbx.ps1") `
    -SourceFbx $SourceFbx `
    -AssetName "luxun_model"
