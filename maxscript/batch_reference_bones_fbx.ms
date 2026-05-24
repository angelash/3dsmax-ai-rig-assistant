/*
Batch reference FBX bone extractor.

This imports one bound/reference FBX and exports the Skin bone references with
world-space node positions plus the same AccuRig-to-Biped semantic labels used
by Stage02 reference weight collapse.
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

fn jsonString value =
(
    local s = value as string
    s = substituteString s "\\" "\\\\"
    s = substituteString s "\"" "\\\""
    s = substituteString s "\n" "\\n"
    "\"" + s + "\""
)

fn jsonNumber value =
(
    formattedPrint (value as float) format:".6f"
)

fn jsonPoint p =
(
    "[" + (jsonNumber p.x) + ", " + (jsonNumber p.y) + ", " + (jsonNumber p.z) + "]"
)

fn jsonBool value =
(
    if value then "true" else "false"
)

fn nodeClassName n =
(
    local cls = ""
    try(cls = (classOf n) as string)catch(cls = "")
    cls
)

fn controllerClassName n =
(
    local cls = ""
    try(cls = (classOf n.controller) as string)catch(cls = "")
    cls
)

fn referenceSemanticForBoneName boneName =
(
    local n = boneName as string
    if n == "" then undefined
    else if matchPattern n pattern:"*RL_BoneRoot*" ignoreCase:true then "Pelvis"
    else if matchPattern n pattern:"*CC_Base_Hip*" ignoreCase:true then "Pelvis"
    else if matchPattern n pattern:"*CC_Base_Pelvis*" ignoreCase:true then "Pelvis"
    else if matchPattern n pattern:"*CC_Base_Waist*" ignoreCase:true then "Spine"
    else if matchPattern n pattern:"*CC_Base_Spine*" ignoreCase:true then "Chest"
    else if matchPattern n pattern:"*CC_Base_Ribs*" ignoreCase:true then "Chest"
    else if matchPattern n pattern:"*CC_Base_*_Ribs*" ignoreCase:true then "Chest"
    else if matchPattern n pattern:"*CC_Base_*_Breast*" ignoreCase:true then "Chest"
    else if matchPattern n pattern:"*CC_Base_Neck*" ignoreCase:true then "Neck"
    else if matchPattern n pattern:"*CC_Base_Head*" ignoreCase:true then "Head"
    else if matchPattern n pattern:"*CC_Base_*Eye*" ignoreCase:true then "Head"
    else if matchPattern n pattern:"*CC_Base_*Jaw*" ignoreCase:true then "Head"
    else if matchPattern n pattern:"*CC_Base_*Tongue*" ignoreCase:true then "Head"
    else if matchPattern n pattern:"*CC_Base_*Teeth*" ignoreCase:true then "Head"
    else if matchPattern n pattern:"*CC_Base_Facial*" ignoreCase:true then "Head"
    else if matchPattern n pattern:"*CC_Base_L_Clavicle*" ignoreCase:true then "L_Clavicle"
    else if matchPattern n pattern:"*CC_Base_L_Upperarm*" ignoreCase:true then "L_UpperArm"
    else if matchPattern n pattern:"*CC_Base_L_Forearm*" ignoreCase:true then "L_Forearm"
    else if matchPattern n pattern:"*CC_Base_L_ElbowShareBone*" ignoreCase:true then "L_Forearm"
    else if matchPattern n pattern:"*CC_Base_L_Hand*" ignoreCase:true then "L_Hand"
    else if matchPattern n pattern:"*CC_Base_R_Clavicle*" ignoreCase:true then "R_Clavicle"
    else if matchPattern n pattern:"*CC_Base_R_Upperarm*" ignoreCase:true then "R_UpperArm"
    else if matchPattern n pattern:"*CC_Base_R_Forearm*" ignoreCase:true then "R_Forearm"
    else if matchPattern n pattern:"*CC_Base_R_ElbowShareBone*" ignoreCase:true then "R_Forearm"
    else if matchPattern n pattern:"*CC_Base_R_Hand*" ignoreCase:true then "R_Hand"
    else if matchPattern n pattern:"*CC_Base_L_Thigh*" ignoreCase:true then "L_Thigh"
    else if matchPattern n pattern:"*CC_Base_L_KneeShareBone*" ignoreCase:true then "L_Calf"
    else if matchPattern n pattern:"*CC_Base_L_Calf*" ignoreCase:true then "L_Calf"
    else if matchPattern n pattern:"*CC_Base_L_Foot*" ignoreCase:true then "L_Foot"
    else if matchPattern n pattern:"*CC_Base_L_Toe*" ignoreCase:true then "L_Toe"
    else if matchPattern n pattern:"*CC_Base_L_*Toe*" ignoreCase:true then "L_Toe"
    else if matchPattern n pattern:"*CC_Base_R_Thigh*" ignoreCase:true then "R_Thigh"
    else if matchPattern n pattern:"*CC_Base_R_KneeShareBone*" ignoreCase:true then "R_Calf"
    else if matchPattern n pattern:"*CC_Base_R_Calf*" ignoreCase:true then "R_Calf"
    else if matchPattern n pattern:"*CC_Base_R_Foot*" ignoreCase:true then "R_Foot"
    else if matchPattern n pattern:"*CC_Base_R_Toe*" ignoreCase:true then "R_Toe"
    else if matchPattern n pattern:"*CC_Base_R_*Toe*" ignoreCase:true then "R_Toe"
    else undefined
)

fn findSkinModifier obj =
(
    local found = undefined
    for m in obj.modifiers while found == undefined do
    (
        if classOf m == Skin do found = m
    )
    found
)

fn safeImportFbx fbxPath =
(
    local beforeCount = objects.count
    local exceptionMessage = ""
    local importThrew = false
    try(importFile fbxPath #noPrompt)
    catch ex
    (
        importThrew = true
        exceptionMessage = ex as string
    )
    local afterCount = objects.count
    if importThrew do format "[AIRA RefBoneExport] Import warning: %\n" exceptionMessage
    afterCount > beforeCount
)

fn getGeometryBounds =
(
    local mn = [0, 0, 0]
    local mx = [0, 0, 0]
    local first = true
    for n in geometry do
    (
        local b = nodeGetBoundingBox n n.transform
        if first then
        (
            mn = b[1]
            mx = b[2]
            first = false
        )
        else
        (
            mn = [amin mn.x b[1].x, amin mn.y b[1].y, amin mn.z b[1].z]
            mx = [amax mx.x b[2].x, amax mx.y b[2].y, amax mx.z b[2].z]
        )
    )
    #(mn, mx)
)

fn writeBoneExport assetName outDir =
(
    ensureDir outDir
    local outPath = outDir + "\\" + assetName + "_reference_bones.json"
    local fp = createFile outPath
    local bounds = getGeometryBounds()
    local mn = bounds[1]
    local mx = bounds[2]
    local size = mx - mn
    local center = (mn + mx) / 2.0
    local skinEntries = #()
    local skinCount = 0

    for obj in geometry do
    (
        local skinMod = findSkinModifier obj
        if skinMod != undefined do
        (
            local boneCount = 0
            try(boneCount = skinOps.GetNumberBones skinMod)catch(boneCount = 0)
            append skinEntries #(obj, skinMod, boneCount)
            skinCount += boneCount
        )
    )

    format "{\n" to:fp
    format "  \"assetName\": %, \n" (jsonString assetName) to:fp
    format "  \"sourceFbx\": %, \n" (jsonString (getEnv "AIRA_REF_FBX_PATH" "")) to:fp
    format "  \"generatedAt\": %, \n" (jsonString (localTime as string)) to:fp
    format "  \"geometryCount\": %, \n" geometry.count to:fp
    format "  \"bounds\": {\"min\": %, \"max\": %, \"size\": %, \"center\": %},\n" (jsonPoint mn) (jsonPoint mx) (jsonPoint size) (jsonPoint center) to:fp
    format "  \"skinObjectCount\": %, \n" skinEntries.count to:fp
    format "  \"skinBoneReferenceCount\": %, \n" skinCount to:fp
    format "  \"skinObjects\": [\n" to:fp
    for s = 1 to skinEntries.count do
    (
        local entry = skinEntries[s]
        local obj = entry[1]
        local boneCount = entry[3]
        format "    {\"name\": %, \"boneCount\": %}%" (jsonString obj.name) boneCount (if s < skinEntries.count then "," else "") to:fp
        format "\n" to:fp
    )
    format "  ],\n" to:fp
    format "  \"skinBones\": [\n" to:fp
    local wrote = 0
    for s = 1 to skinEntries.count do
    (
        local entry = skinEntries[s]
        local skinObj = entry[1]
        local skinMod = entry[2]
        local boneCount = entry[3]
        for i = 1 to boneCount do
        (
            local boneName = ""
            local boneNode = undefined
            try(boneName = skinOps.GetBoneName skinMod i 0)catch(boneName = "")
            try(boneNode = skinOps.GetBoneNode skinMod i)catch(boneNode = undefined)
            if wrote > 0 do format ",\n" to:fp
            wrote += 1
            local pos = [0, 0, 0]
            local parentName = ""
            local className = ""
            local controllerName = ""
            local exists = false
            if boneNode != undefined do
            (
                exists = true
                try(pos = boneNode.pos)catch()
                try(parentName = boneNode.parent.name)catch(parentName = "")
                className = nodeClassName boneNode
                controllerName = controllerClassName boneNode
            )
            local semantic = referenceSemanticForBoneName boneName
            format "    {\"skinObject\": %, \"index\": %, \"name\": %, \"semantic\": %, \"nodeFound\": %, \"position\": %, \"parent\": %, \"class\": %, \"controller\": %}" \
                (jsonString skinObj.name) i (jsonString boneName) (if semantic == undefined then "null" else jsonString semantic) (jsonBool exists) (jsonPoint pos) (jsonString parentName) (jsonString className) (jsonString controllerName) to:fp
        )
    )
    format "\n  ]\n" to:fp
    format "}\n" to:fp
    close fp
    outPath
)

fn main =
(
    local fbxPath = getEnv "AIRA_REF_FBX_PATH" ""
    local assetName = getEnv "AIRA_REF_ASSET_NAME" "reference_asset"
    local outDir = getEnv "AIRA_REF_OUT_DIR" @"F:\workspace\github\3dsmax-ai-rig-assistant\out\reference_bones"
    if fbxPath == "" or not doesFileExist fbxPath do throw ("FBX file not found: " + fbxPath)
    resetMaxFile #noPrompt
    local importOk = safeImportFbx fbxPath
    if not importOk do throw ("No objects imported from FBX: " + fbxPath)
    local outPath = writeBoneExport assetName outDir
    format "[AIRA RefBoneExport] JSON: %\n" outPath
    quitMAX #noPrompt
    true
)

main()
