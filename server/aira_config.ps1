$script:AiraConfigModuleRoot = $PSScriptRoot
$script:AiraConfigToolRoot = Split-Path -Parent $script:AiraConfigModuleRoot

function Get-AiraToolRoot {
    $envRoot = [Environment]::GetEnvironmentVariable("AIRA_TOOL_ROOT", "Process")
    if (-not [string]::IsNullOrWhiteSpace($envRoot)) {
        return [System.IO.Path]::GetFullPath([Environment]::ExpandEnvironmentVariables($envRoot))
    }
    return [System.IO.Path]::GetFullPath($script:AiraConfigToolRoot)
}

function ConvertTo-AiraAbsolutePath {
    param(
        [string]$PathValue,
        [string]$BasePath = (Get-AiraToolRoot)
    )

    if ([string]::IsNullOrWhiteSpace($PathValue)) {
        return ""
    }

    $Expanded = [Environment]::ExpandEnvironmentVariables($PathValue)
    if ([System.IO.Path]::IsPathRooted($Expanded)) {
        return [System.IO.Path]::GetFullPath($Expanded)
    }
    return [System.IO.Path]::GetFullPath((Join-Path $BasePath $Expanded))
}

function Get-AiraLocalConfigPath {
    Join-Path (Get-AiraToolRoot) "config\local.json"
}

function Get-AiraLocalConfig {
    $ConfigPath = Get-AiraLocalConfigPath
    if (Test-Path -LiteralPath $ConfigPath -PathType Leaf) {
        return Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json
    }
    return [pscustomobject]@{}
}

function Get-AiraObjectValue {
    param(
        [object]$Object,
        [string]$Path
    )

    if ($null -eq $Object -or [string]::IsNullOrWhiteSpace($Path)) {
        return $null
    }

    $Current = $Object
    foreach ($Part in $Path.Split(".")) {
        if ($null -eq $Current) {
            return $null
        }
        $Property = $Current.PSObject.Properties[$Part]
        if ($null -eq $Property) {
            return $null
        }
        $Current = $Property.Value
    }
    return $Current
}

function Get-AiraSetting {
    param(
        [string]$Name,
        [string]$EnvName = "",
        [object]$Default = ""
    )

    if (-not [string]::IsNullOrWhiteSpace($EnvName)) {
        $EnvValue = [Environment]::GetEnvironmentVariable($EnvName, "Process")
        if (-not [string]::IsNullOrWhiteSpace($EnvValue)) {
            return $EnvValue
        }
    }

    $Config = Get-AiraLocalConfig
    $Value = Get-AiraObjectValue -Object $Config -Path $Name
    if ($null -ne $Value -and -not [string]::IsNullOrWhiteSpace([string]$Value)) {
        return $Value
    }
    return $Default
}

function Get-AiraSourceRoot {
    ConvertTo-AiraAbsolutePath (Get-AiraSetting -Name "sourceRoot" -EnvName "AIRA_SOURCE_ROOT" -Default "source")
}

function Get-AiraOutDir {
    ConvertTo-AiraAbsolutePath (Get-AiraSetting -Name "outDir" -EnvName "AIRA_OUT_DIR" -Default "out")
}

function Get-AiraReportRoot {
    ConvertTo-AiraAbsolutePath (Get-AiraSetting -Name "reportRoot" -EnvName "AIRA_REPORT_ROOT" -Default "report")
}

function Get-AiraPythonPath {
    ConvertTo-AiraAbsolutePath (Get-AiraSetting -Name "python" -EnvName "AIRA_PYTHON" -Default ".venv\Scripts\python.exe")
}

function Get-AiraBridgeHost {
    [string](Get-AiraSetting -Name "bridge.host" -EnvName "AIRA_MCP_HOST" -Default "127.0.0.1")
}

function Get-AiraBridgePort {
    [int](Get-AiraSetting -Name "bridge.port" -EnvName "AIRA_MCP_PORT" -Default 37820)
}

function Find-AiraMaxBatch {
    $Candidates = @()
    $Configured = [string](Get-AiraSetting -Name "maxBatch" -EnvName "AIRA_MAXBATCH" -Default "")
    if (-not [string]::IsNullOrWhiteSpace($Configured)) {
        $Candidates += (ConvertTo-AiraAbsolutePath $Configured)
    }

    $Roots = @($env:ProgramW6432, $env:ProgramFiles, ${env:ProgramFiles(x86)}, "C:\Program Files", "D:\Program files")
    $Versions = @(2026, 2025, 2024, 2023, 2022, 2021, 2020)
    foreach ($Root in $Roots) {
        if ([string]::IsNullOrWhiteSpace($Root)) {
            continue
        }
        foreach ($Version in $Versions) {
            $Candidates += (Join-Path $Root "Autodesk\3ds Max $Version\3dsmaxbatch.exe")
        }
    }

    foreach ($Candidate in ($Candidates | Select-Object -Unique)) {
        if (Test-Path -LiteralPath $Candidate -PathType Leaf) {
            return $Candidate
        }
    }

    if ($Candidates.Count -gt 0) {
        return $Candidates[0]
    }
    return ""
}

function Get-AiraMaxBatch {
    param([string]$Override = "")

    if (-not [string]::IsNullOrWhiteSpace($Override)) {
        return ConvertTo-AiraAbsolutePath $Override
    }
    return Find-AiraMaxBatch
}

function Set-AiraProcessEnvironmentFromConfig {
    $ToolRoot = Get-AiraToolRoot
    $env:AIRA_TOOL_ROOT = $ToolRoot
    $env:AIRA_SOURCE_ROOT = Get-AiraSourceRoot
    $env:AIRA_OUT_DIR = Get-AiraOutDir
    $env:AIRA_REPORT_ROOT = Get-AiraReportRoot
    $env:AIRA_MCP_HOST = Get-AiraBridgeHost
    $env:AIRA_MCP_PORT = [string](Get-AiraBridgePort)

    $MaxBatch = Find-AiraMaxBatch
    if (-not [string]::IsNullOrWhiteSpace($MaxBatch)) {
        $env:AIRA_MAXBATCH = $MaxBatch
    }

    [pscustomobject]@{
        toolRoot = $ToolRoot
        sourceRoot = $env:AIRA_SOURCE_ROOT
        outDir = $env:AIRA_OUT_DIR
        reportRoot = $env:AIRA_REPORT_ROOT
        python = Get-AiraPythonPath
        maxBatch = $env:AIRA_MAXBATCH
        bridgeHost = $env:AIRA_MCP_HOST
        bridgePort = [int]$env:AIRA_MCP_PORT
    }
}
