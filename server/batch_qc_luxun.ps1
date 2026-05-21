$ErrorActionPreference = "Stop"

$ToolRoot = "F:\workspace\github\3dsmax-ai-rig-assistant"
$SourceFbx = Join-Path $ToolRoot "source\luxun_model\陆逊模型.fbx"
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

& (Join-Path $ScriptRoot "batch_qc_fbx.ps1") `
    -SourceFbx $SourceFbx `
    -AssetName "luxun_model"
