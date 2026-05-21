/*
Batch runner for AIRA Stage02 Skin setup.

Environment:
- AIRA_STAGE02_SOURCE_MAX
- AIRA_STAGE02_ASSET_NAME
- AIRA_STAGE02_OUT_DIR
- AIRA_STAGE02_BONE_AFFECT_LIMIT
- AIRA_STAGE02_STAGE01_GATE_STATUS
- AIRA_STAGE02_STAGE01_GATE_JSON
*/

global AIRA_STAGE02_HEADLESS = true
global AIRA_Stage02
global AIRA_AssetQC

fn ensureDir path =
(
    if not (doesDirectoryExist path) do makeDir path all:true
)

fn joinPath dir fileName =
(
    local d = dir as string
    if d == "" then fileName
    else
    (
        local lastChar = substring d d.count 1
        if lastChar == "\\" or lastChar == "/" then d + fileName else d + "\\" + fileName
    )
)

fn getEnv key defaultValue =
(
    local value = (dotNetClass "System.Environment").GetEnvironmentVariable key
    if value == undefined or value == "" then defaultValue else value
)

fn writeLine fp text =
(
    format "%\n" text to:fp
)

fn main =
(
    local toolRoot = @"F:\workspace\github\3dsmax-ai-rig-assistant"
    local sourceMax = getEnv "AIRA_STAGE02_SOURCE_MAX" ""
    local assetName = getEnv "AIRA_STAGE02_ASSET_NAME" "stage02_asset"
    local outDir = getEnv "AIRA_STAGE02_OUT_DIR" (toolRoot + @"\out\stage02_current_scene")
    local affectLimit = (getEnv "AIRA_STAGE02_BONE_AFFECT_LIMIT" "3") as integer
    local gateStatus = getEnv "AIRA_STAGE02_STAGE01_GATE_STATUS" "not_provided"
    local stage02Path = toolRoot + @"\maxscript\aira_stage02_skin.ms"
    local assetQcPath = toolRoot + @"\maxscript\aira_asset_qc.ms"
    local sceneDir = joinPath outDir "scene"
    local reportsDir = joinPath outDir "reports"
    local dataDir = joinPath outDir "data"
    local logsDir = joinPath outDir "logs"
    local summaryPath = joinPath reportsDir (assetName + "_stage02_batch_summary.md")
    local scenePath = joinPath sceneDir (assetName + "_stage02_skin_scene.max")

    ensureDir outDir
    ensureDir sceneDir
    ensureDir reportsDir
    ensureDir dataDir
    ensureDir logsDir

    local fp = createFile summaryPath
    writeLine fp ("# Stage02 Skin Batch: " + assetName)
    writeLine fp ""
    writeLine fp ("- Source scene: `" + sourceMax + "`")
    writeLine fp ("- Stage01 gate status: `" + gateStatus + "`")
    writeLine fp ("- Bone affect limit: `" + (affectLimit as string) + "`")
    writeLine fp ("- Started: `" + (localTime as string) + "`")

    if sourceMax == "" or not (doesFileExist sourceMax) then
    (
        writeLine fp "- Load source scene: `failed`"
        close fp
        quitMAX #noPrompt
        return false
    )

    resetMaxFile #noPrompt
    local loadOk = true
    try(loadMaxFile sourceMax quiet:true)catch(loadOk = false)
    writeLine fp ("- Load source scene OK: `" + (loadOk as string) + "`")

    if loadOk then
    (
        fileIn stage02Path
        AIRA_Stage02.outDir = outDir
        AIRA_Stage02.boneAffectLimit = affectLimit
        AIRA_Stage02.maxAssignedInfluences = affectLimit
        local report = AIRA_Stage02.runInitialSkin assetName
        writeLine fp ("- Stage02 report JSON: `" + report[1] + "`")
        writeLine fp ("- Stage02 report Markdown: `" + report[2] + "`")
        writeLine fp ("- Stage02 skin setup ready: `" + (report[3] as string) + "`")
        writeLine fp ("- Stage02 issue count: `" + (report[4] as string) + "`")

        fileIn assetQcPath
        AIRA_AssetQC.outDir = dataDir
        local assetQc = AIRA_AssetQC.writeReports (assetName + "_stage02_skin")
        writeLine fp ("- Stage02 asset QC JSON: `" + assetQc[1] + "`")
        writeLine fp ("- Stage02 asset QC Markdown: `" + assetQc[2] + "`")
        writeLine fp ("- Stage02 asset QC issue count: `" + (assetQc[3] as string) + "`")

        saveMaxFile scenePath
        writeLine fp ("- Saved scene: `" + scenePath + "`")
    )

    writeLine fp ("- Finished: `" + (localTime as string) + "`")
    close fp
    format "[AIRA Stage02 Batch] Summary: %\n" summaryPath
    quitMAX #noPrompt
    true
)

main()
