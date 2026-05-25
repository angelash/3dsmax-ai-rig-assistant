/*
Batch asset QC for one FBX file.

Run through F:/workspace/github/3dsmax-ai-rig-assistant/server/batch_qc_luxun.ps1
*/

global AIRA_AssetQC

fn ensureDir path =
(
    if not (doesDirectoryExist path) do makeDir path all:true
)

fn getEnv key defaultValue =
(
    local value = (dotNetClass "System.Environment").GetEnvironmentVariable key
    if value == undefined or value == "" then defaultValue else value
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

fn appendDirIfExists dirs dir =
(
    if dir != undefined and dir != "" and doesDirectoryExist dir and (findItem dirs dir) == 0 do append dirs dir
)

fn textureSearchDirs fbxPath assetName envKey =
(
    local dirs = #()
    appendDirIfExists dirs (getEnv envKey "")
    local fbxDir = getFilenamePath fbxPath
    appendDirIfExists dirs (joinPath fbxDir (assetName + ".fbm"))
    appendDirIfExists dirs (joinPath fbxDir ((getFilenameFile fbxPath) + ".fbm"))
    dirs
)

fn relinkBitmapsToLocalSidecar fbxPath assetName envKey =
(
    local dirs = textureSearchDirs fbxPath assetName envKey
    local bitmaps = #()
    local relinked = 0
    local unresolved = 0
    try(bitmaps = getClassInstances Bitmaptexture)catch(bitmaps = #())

    for b in bitmaps do
    (
        local original = ""
        try(original = b.filename as string)catch(original = "")
        if original != "" do
        (
            local fileName = filenameFromPath original
            local foundPath = ""
            for dir in dirs while foundPath == "" do
            (
                local candidate = joinPath dir fileName
                if doesFileExist candidate do foundPath = candidate
            )
            if foundPath != "" then
            (
                try
                (
                    b.filename = assetName + ".fbm\\" + fileName
                    relinked += 1
                )
                catch()
            )
            else
            (
                unresolved += 1
            )
        )
    )
    #(relinked, unresolved, dirs.count)
)

fn safeImportFbx fbxPath =
(
    local beforeCount = geometry.count
    local exceptionMessage = ""
    local importThrew = false

    try
    (
        importFile fbxPath #noPrompt
    )
    catch ex
    (
        importThrew = true
        exceptionMessage = ex as string
    )

    local afterCount = geometry.count
    if importThrew do
    (
        if afterCount > beforeCount then
            format "[AIRA AssetQC] FBX import completed with importer warning: %\n" exceptionMessage
        else
            format "[AIRA AssetQC] FBX import failed: %\n" exceptionMessage
    )

    afterCount > beforeCount
)

fn main =
(
    local toolRoot = getEnv "AIRA_TOOL_ROOT" "."
    local outDir = getEnv "AIRA_QC_OUT_DIR" (getEnv "AIRA_OUT_DIR" (joinPath toolRoot "out"))
    local sourceRoot = getEnv "AIRA_SOURCE_ROOT" (joinPath toolRoot "source")
    local asciiFbxPath = outDir + @"\luxun_model.fbx"
    local fallbackFbxPath = joinPath sourceRoot @"luxun_model\陆逊模型.fbx"
    local fbxPath = getEnv "AIRA_QC_FBX_PATH" (if doesFileExist asciiFbxPath then asciiFbxPath else fallbackFbxPath)
    local assetName = getEnv "AIRA_QC_ASSET_NAME" (getFilenameFile fbxPath)
    local qcPath = joinPath (joinPath toolRoot "maxscript") "aira_asset_qc.ms"
    local scenePath = outDir + @"\" + assetName + @"_raw_asset_qc_scene.max"

    ensureDir outDir
    resetMaxFile #noPrompt

    local importOk = safeImportFbx fbxPath
    local textureRelink = relinkBitmapsToLocalSidecar fbxPath assetName "AIRA_QC_TEXTURE_DIR"
    local geoNodes = for n in geometry collect n
    if geoNodes.count > 0 do importOk = true
    if not importOk do throw ("No geometry imported from FBX: " + fbxPath)

    fileIn qcPath
    AIRA_AssetQC.outDir = outDir
    local result = AIRA_AssetQC.writeReports assetName
    saveMaxFile scenePath

    format "[AIRA AssetQC] Import OK: %\n" importOk
    format "[AIRA AssetQC] Texture bitmap relinked: %\n" textureRelink[1]
    format "[AIRA AssetQC] Texture bitmap unresolved: %\n" textureRelink[2]
    format "[AIRA AssetQC] Texture search dirs: %\n" textureRelink[3]
    format "[AIRA AssetQC] Geometry nodes: %\n" geoNodes.count
    format "[AIRA AssetQC] JSON: %\n" result[1]
    format "[AIRA AssetQC] Markdown: %\n" result[2]
    format "[AIRA AssetQC] Issues: %\n" result[3]
    quitMAX #noPrompt
    true
)

main()
