/*
Export one FBX mesh to OBJ for external geometry/skeletonization algorithms.
*/

fn ensureDir path =
(
    if not (doesDirectoryExist path) do makeDir path all:true
)

fn getEnv key defaultValue =
(
    local value = (dotNetClass "System.Environment").GetEnvironmentVariable key
    if value == undefined or value == "" then defaultValue else value
)

fn safeImportFbx fbxPath =
(
    local beforeCount = geometry.count
    try(importFile fbxPath #noPrompt)catch()
    geometry.count > beforeCount
)

fn main =
(
    local outDir = @"F:\workspace\github\3dsmax-ai-rig-assistant\out"
    local fbxPath = getEnv "AIRA_EXPORT_FBX_PATH" (outDir + @"\luxun_model.fbx")
    local assetName = getEnv "AIRA_EXPORT_ASSET_NAME" "luxun_model"
    local objPath = outDir + @"\" + assetName + @".obj"

    ensureDir outDir
    resetMaxFile #noPrompt

    local ok = safeImportFbx fbxPath
    if not ok do throw ("No geometry imported from FBX: " + fbxPath)

    local nodes = for n in geometry collect n
    select nodes
    exportFile objPath #noPrompt selectedOnly:true
    format "[AIRA Export] OBJ: %\n" objPath
    quitMAX #noPrompt
    true
)

main()
