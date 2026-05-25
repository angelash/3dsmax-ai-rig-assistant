/*
AI Rig Assistant - Asset QC Tool
Target: 3ds Max 2020+ / MAXScript

Production-oriented asset inspection:
- geometry count, vertices, triangle faces, bounds
- material and bitmap path checks
- transform / origin / scale checks
- bone-like nodes and Skin modifier checks
- basic body-ratio signals that are safe to infer
- JSON and Markdown reports for AI interpretation
*/

global AIRA_AssetQC

fn AIRA_assetQcGetEnv key defaultValue =
(
    local value = (dotNetClass "System.Environment").GetEnvironmentVariable key
    if value == undefined or value == "" then defaultValue else value
)

fn AIRA_assetQcJoinPath dir fileName =
(
    local d = dir as string
    if d == "" then fileName
    else
    (
        local lastChar = substring d d.count 1
        if lastChar == "\\" or lastChar == "/" then d + fileName else d + "\\" + fileName
    )
)

fn AIRA_assetQcToolRoot =
(
    local envRoot = AIRA_assetQcGetEnv "AIRA_TOOL_ROOT" ""
    if envRoot != "" then envRoot
    else
    (
        local sourceFile = ""
        try(sourceFile = getSourceFileName())catch(sourceFile = "")
        if sourceFile != undefined and sourceFile != "" then
        (
            local di = dotNetObject "System.IO.DirectoryInfo" (getFilenamePath sourceFile)
            di.Parent.FullName
        )
        else "."
    )
)

fn AIRA_assetQcDefaultOutDir =
(
    local outDir = AIRA_assetQcGetEnv "AIRA_QC_OUT_DIR" ""
    if outDir == "" do outDir = AIRA_assetQcGetEnv "AIRA_OUT_DIR" ""
    if outDir == "" do outDir = AIRA_assetQcJoinPath (AIRA_assetQcToolRoot()) "out"
    outDir
)

struct AIRAAssetQCTool
(
    outDir = AIRA_assetQcDefaultOutDir(),
    triangleLimit = 12000,
    vertexInfluenceLimit = 4,
    originTolerance = 0.01,
    unitMinHeight = 0.1,
    unitMaxHeight = 10.0,

    fn ensureDir path =
    (
        if not (doesDirectoryExist path) do makeDir path all:true
    ),

    fn jsonEscape value =
    (
        local s = value as string
        s = substituteString s "\\" "\\\\"
        s = substituteString s "\"" "\\\""
        s = substituteString s "\r" "\\r"
        s = substituteString s "\n" "\\n"
        s = substituteString s "\t" "\\t"
        s
    ),

    fn jsonString value =
    (
        "\"" + jsonEscape value + "\""
    ),

    fn jsonBool value =
    (
        if value then "true" else "false"
    ),

    fn jsonNumber value =
    (
        formattedPrint value format:".6f"
    ),

    fn jsonPoint p =
    (
        "[" + jsonNumber p.x + "," + jsonNumber p.y + "," + jsonNumber p.z + "]"
    ),

    fn jsonStringArray items =
    (
        local s = "["
        for i = 1 to items.count do
        (
            s += jsonString items[i]
            if i < items.count do s += ","
        )
        s + "]"
    ),

    fn appendUnique arr value =
    (
        if value != undefined and (findItem arr value) == 0 do append arr value
    ),

    fn minPoint a b =
    (
        [(if a.x < b.x then a.x else b.x), (if a.y < b.y then a.y else b.y), (if a.z < b.z then a.z else b.z)]
    ),

    fn maxPoint a b =
    (
        [(if a.x > b.x then a.x else b.x), (if a.y > b.y then a.y else b.y), (if a.z > b.z then a.z else b.z)]
    ),

    fn getBounds nodes =
    (
        if nodes == undefined or nodes.count == 0 then undefined
        else
        (
            local mn = [1e9, 1e9, 1e9]
            local mx = [-1e9, -1e9, -1e9]
            for n in nodes do
            (
                try
                (
                    mn = minPoint mn n.min
                    mx = maxPoint mx n.max
                )
                catch()
            )
            if mn.x == 1e9 then undefined else #(mn, mx)
        )
    ),

    fn nodeClassName n =
    (
        try((classOf n) as string)catch("unknown")
    ),

    fn controllerClassName n =
    (
        try((classOf n.controller) as string)catch("unknown")
    ),

    fn isRigNode n =
    (
        if not (isValidNode n) then false
        else
        (
            local cls = nodeClassName n
            local ctrlCls = controllerClassName n
            local hasFigure = false
            try(hasFigure = isProperty n.controller #figureMode)catch(hasFigure = false)
            hasFigure or \
            (matchPattern n.name pattern:"AIRA_GUIDE_*" ignoreCase:true) or \
            (matchPattern n.name pattern:"AIRA_BONE_*" ignoreCase:true) or \
            (matchPattern n.name pattern:"AIRA_Biped*" ignoreCase:true) or \
            (matchPattern n.name pattern:"Bip*" ignoreCase:true) or \
            (matchPattern cls pattern:"*Bone*" ignoreCase:true) or \
            (matchPattern cls pattern:"*Biped*" ignoreCase:true) or \
            (matchPattern ctrlCls pattern:"*Bip*" ignoreCase:true)
        )
    ),

    fn isAssetGeometry n =
    (
        if not (isValidNode n) then false
        else if isRigNode n then false
        else true
    ),

    fn geometryNodes =
    (
        for n in geometry where isAssetGeometry n collect n
    ),

    fn countTriFaces nodes =
    (
        local total = 0
        for n in nodes do
        (
            try
            (
                local tri = snapshotAsMesh n
                total += tri.numfaces
                delete tri
            )
            catch()
        )
        total
    ),

    fn countMeshVertices nodes =
    (
        local total = 0
        for n in nodes do
        (
            try
            (
                local tri = snapshotAsMesh n
                total += tri.numverts
                delete tri
            )
            catch()
        )
        total
    ),

    fn materialNames nodes =
    (
        local names = #()
        for n in nodes do
        (
            try
            (
                if n.material != undefined do appendUnique names n.material.name
            )
            catch()
        )
        names
    ),

    fn bitmapPaths =
    (
        local paths = #()
        local bitmaps = #()
        try(bitmaps = getClassInstances Bitmaptexture)catch(bitmaps = #())
        for b in bitmaps do
        (
            try
            (
                if b.filename != undefined and b.filename != "" do appendUnique paths b.filename
            )
            catch()
        )
        paths
    ),

    fn isAbsolutePath path =
    (
        local p = path as string
        (matchPattern p pattern:"?:\\*" ignoreCase:true) or (matchPattern p pattern:"//*" ignoreCase:true) or (matchPattern p pattern:"\\\\*" ignoreCase:true)
    ),

    fn joinPath dir fileName =
    (
        local d = dir as string
        if d == "" then fileName
        else
        (
            local lastChar = substring d d.count 1
            if lastChar == "\\" or lastChar == "/" then d + fileName else d + "\\" + fileName
        )
    ),

    fn appendDirIfExists dirs dir =
    (
        if dir != undefined and dir != "" and doesDirectoryExist dir and (findItem dirs dir) == 0 do append dirs dir
    ),

    fn textureSearchDirs =
    (
        local dirs = #()
        local stageDir = (dotNetClass "System.Environment").GetEnvironmentVariable "AIRA_STAGE01_TEXTURE_DIR"
        local qcDir = (dotNetClass "System.Environment").GetEnvironmentVariable "AIRA_QC_TEXTURE_DIR"
        appendDirIfExists dirs stageDir
        appendDirIfExists dirs qcDir
        if maxFilePath != undefined and maxFilePath != "" do appendDirIfExists dirs maxFilePath
        dirs
    ),

    fn bitmapPathExists path =
    (
        local p = path as string
        if p == "" then false
        else if doesFileExist p then true
        else
        (
            local found = false
            local fileName = filenameFromPath p
            for dir in textureSearchDirs() while not found do
            (
                if doesFileExist (joinPath dir p) do found = true
                if not found and fileName != "" and doesFileExist (joinPath dir fileName) do found = true
            )
            found
        )
    ),

    fn findSkinModifier obj =
    (
        local found = undefined
        try
        (
            for m in obj.modifiers while found == undefined do
            (
                if classOf m == Skin do found = m
            )
        )
        catch()
        found
    ),

    fn analyzeSkin nodes =
    (
        local skinObjects = #()
        local totalSkinBones = 0
        local maxInfluences = 0
        local zeroWeightVertices = 0
        local verticesChecked = 0

        for obj in nodes do
        (
            local skinMod = findSkinModifier obj
            if skinMod != undefined do
            (
                append skinObjects obj.name
                local boneCount = 0
                try(boneCount = skinOps.GetNumberBones skinMod)catch(boneCount = 0)
                totalSkinBones += boneCount

                local vCount = 0
                try(vCount = skinOps.GetNumberVertices skinMod)catch(vCount = 0)
                for v = 1 to vCount do
                (
                    local weightCount = undefined
                    try(weightCount = skinOps.GetVertexWeightCount skinMod v)catch(weightCount = undefined)
                    if weightCount != undefined do
                    (
                        verticesChecked += 1
                        if weightCount > maxInfluences do maxInfluences = weightCount
                        if weightCount == 0 do zeroWeightVertices += 1
                    )
                )
            )
        )

        #(skinObjects, totalSkinBones, maxInfluences, zeroWeightVertices, verticesChecked)
    ),

    fn boneLikeNodes =
    (
        local nodes = #()
        for n in objects do
        (
            local cls = nodeClassName n
            local ctrlCls = controllerClassName n
            local isBip = false
            try(isBip = isProperty n.controller #figureMode)catch(isBip = false)
            if isBip or \
                (matchPattern cls pattern:"*Bone*" ignoreCase:true) or \
                (matchPattern cls pattern:"*Biped*" ignoreCase:true) or \
                (matchPattern ctrlCls pattern:"*Bip*" ignoreCase:true) or \
                (matchPattern n.name pattern:"AIRA_BONE_*" ignoreCase:true) or \
                (matchPattern n.name pattern:"*Bip*" ignoreCase:true) or \
                (matchPattern n.name pattern:"*bone*" ignoreCase:true) do
            (
                append nodes n
            )
        )
        nodes
    ),

    fn nonUniformScaleNodes nodes =
    (
        local bad = #()
        for n in nodes do
        (
            try
            (
                local s = n.scale
                if (abs(s.x - s.y) > 0.001) or (abs(s.x - s.z) > 0.001) or (abs(s.y - s.z) > 0.001) do append bad n.name
            )
            catch()
        )
        bad
    ),

    fn nonFrozenScaleNodes nodes =
    (
        local bad = #()
        for n in nodes do
        (
            try
            (
                local s = n.scale
                if (abs(s.x - 1.0) > 0.001) or (abs(s.y - 1.0) > 0.001) or (abs(s.z - 1.0) > 0.001) do append bad n.name
            )
            catch()
        )
        bad
    ),

    fn findHeadGeometryHeight nodes =
    (
        local headNodes = for n in nodes where (matchPattern n.name pattern:"*head*" ignoreCase:true) or (matchPattern n.name pattern:"*tou*" ignoreCase:true) collect n
        local b = getBounds headNodes
        if b == undefined then undefined else abs(b[2].z - b[1].z)
    ),

    fn writeReports assetName =
    (
        ensureDir outDir

        local nodes = geometryNodes()
        local bounds = getBounds nodes
        local triCount = countTriFaces nodes
        local vertexCount = countMeshVertices nodes
        local mats = materialNames nodes
        local bitmapFiles = bitmapPaths()
        local missingMaps = #()
        local absoluteMaps = #()
        local issues = #()

        for p in bitmapFiles do
        (
            if not (bitmapPathExists p) do appendUnique missingMaps p
            if isAbsolutePath p do appendUnique absoluteMaps p
        )

        local skins = analyzeSkin nodes
        local skinObjects = skins[1]
        local skinBoneCount = skins[2]
        local maxInfluences = skins[3]
        local zeroWeightVertices = skins[4]
        local verticesChecked = skins[5]
        local bones = boneLikeNodes()
        local nonUniform = nonUniformScaleNodes nodes
        local nonFrozen = nonFrozenScaleNodes nodes

        local mn = [0, 0, 0]
        local mx = [0, 0, 0]
        local size = [0, 0, 0]
        local center = [0, 0, 0]
        local height = 0.0
        local width = 0.0
        local depth = 0.0
        local widthHeightRatio = 0.0
        local headHeight = undefined
        local headBodyRatioText = "null"
        local headRatioMethod = "unavailable"

        if bounds != undefined do
        (
            mn = bounds[1]
            mx = bounds[2]
            size = mx - mn
            center = (mn + mx) / 2.0
            height = abs(size.z)
            width = abs(size.x)
            depth = abs(size.y)
            if height > 0.0001 do widthHeightRatio = (if width > depth then width else depth) / height
            headHeight = findHeadGeometryHeight nodes
            if headHeight != undefined and headHeight > 0.0001 do
            (
                headBodyRatioText = jsonNumber (height / headHeight)
                headRatioMethod = "head_named_geometry"
            )
        )

        if nodes.count == 0 do append issues "No geometry nodes found."
        if triCount > triangleLimit do append issues ("Triangle count exceeds limit: " + (triCount as string) + " > " + (triangleLimit as string))
        if height < unitMinHeight do append issues ("Model height looks too small: " + (height as string))
        if height > unitMaxHeight do append issues ("Model height looks too large for normalized game asset: " + (height as string))
        if abs(mn.z) > originTolerance do append issues ("Model bottom is not near Z=0. bottomZ=" + (mn.z as string))
        if (abs(center.x) > originTolerance) or (abs(center.y) > originTolerance) do append issues ("Model is not centered around origin in X/Y. center=" + (center as string))
        if nonUniform.count > 0 do append issues ("Non-uniform scale nodes: " + (nonUniform.count as string))
        if nonFrozen.count > 0 do append issues ("Non-frozen scale nodes: " + (nonFrozen.count as string))
        if skinObjects.count == 0 do append issues "No Skin modifier found. This is OK for raw model QC, but not OK for bound character delivery."
        if bones.count == 0 do append issues "No bone-like nodes found."
        if maxInfluences > vertexInfluenceLimit do append issues ("Max skin influences per vertex exceeds limit: " + (maxInfluences as string))
        if zeroWeightVertices > 0 do append issues ("Skin has zero-weight vertices: " + (zeroWeightVertices as string))
        if missingMaps.count > 0 do append issues ("Missing bitmap files: " + (missingMaps.count as string))
        if absoluteMaps.count > 0 do append issues ("Absolute bitmap paths found: " + (absoluteMaps.count as string))
        if headHeight == undefined do append issues "Head/body ratio unavailable: no head-named geometry was found."

        local jsonPath = outDir + "\\" + assetName + "_asset_qc.json"
        local mdPath = outDir + "\\" + assetName + "_asset_qc.md"

        local fp = createFile jsonPath
        format "{\n" to:fp
        format "  \"assetName\": %, \n" (jsonString assetName) to:fp
        format "  \"scene\": %, \n" (jsonString (maxFilePath + maxFileName)) to:fp
        format "  \"generatedAt\": %, \n" (jsonString (localTime as string)) to:fp
        format "  \"mesh\": {\n" to:fp
        format "    \"geometryCount\": %, \n" nodes.count to:fp
        format "    \"triangleCount\": %, \n" triCount to:fp
        format "    \"vertexCount\": %, \n" vertexCount to:fp
        format "    \"materialCount\": %\n" mats.count to:fp
        format "  },\n" to:fp
        format "  \"bounds\": {\n" to:fp
        format "    \"min\": %, \n" (jsonPoint mn) to:fp
        format "    \"max\": %, \n" (jsonPoint mx) to:fp
        format "    \"size\": %, \n" (jsonPoint size) to:fp
        format "    \"center\": %, \n" (jsonPoint center) to:fp
        format "    \"height\": %, \n" (jsonNumber height) to:fp
        format "    \"width\": %, \n" (jsonNumber width) to:fp
        format "    \"depth\": %\n" (jsonNumber depth) to:fp
        format "  },\n" to:fp
        format "  \"bodyRatio\": {\n" to:fp
        format "    \"widthHeightRatio\": %, \n" (jsonNumber widthHeightRatio) to:fp
        format "    \"headBodyRatio\": %, \n" headBodyRatioText to:fp
        format "    \"headRatioMethod\": %\n" (jsonString headRatioMethod) to:fp
        format "  },\n" to:fp
        format "  \"transform\": {\n" to:fp
        format "    \"nonUniformScaleNodes\": %, \n" (jsonStringArray nonUniform) to:fp
        format "    \"nonFrozenScaleNodes\": %, \n" (jsonStringArray nonFrozen) to:fp
        format "    \"bottomNearZero\": %, \n" (jsonBool (abs(mn.z) <= originTolerance)) to:fp
        format "    \"centeredXY\": %\n" (jsonBool ((abs(center.x) <= originTolerance) and (abs(center.y) <= originTolerance))) to:fp
        format "  },\n" to:fp
        format "  \"materials\": {\n" to:fp
        format "    \"materialNames\": %, \n" (jsonStringArray mats) to:fp
        format "    \"bitmapCount\": %, \n" bitmapFiles.count to:fp
        format "    \"missingTextures\": %, \n" (jsonStringArray missingMaps) to:fp
        format "    \"absoluteTexturePaths\": %\n" (jsonStringArray absoluteMaps) to:fp
        format "  },\n" to:fp
        format "  \"skeleton\": {\n" to:fp
        format "    \"boneLikeNodeCount\": %, \n" bones.count to:fp
        format "    \"hasSkin\": %, \n" (jsonBool (skinObjects.count > 0)) to:fp
        format "    \"skinObjects\": %, \n" (jsonStringArray skinObjects) to:fp
        format "    \"skinBoneReferenceCount\": %, \n" skinBoneCount to:fp
        format "    \"maxInfluencePerVertex\": %, \n" maxInfluences to:fp
        format "    \"zeroWeightVertices\": %, \n" zeroWeightVertices to:fp
        format "    \"verticesChecked\": %\n" verticesChecked to:fp
        format "  },\n" to:fp
        format "  \"issues\": %\n" (jsonStringArray issues) to:fp
        format "}\n" to:fp
        close fp

        fp = createFile mdPath
        format "# Asset QC Report: %\n\n" assetName to:fp
        format "- Scene: `%`\n" (maxFilePath + maxFileName) to:fp
        format "- Generated: `%`\n" localTime to:fp
        format "- Geometry nodes: `%`\n" nodes.count to:fp
        format "- Triangle faces: `%`\n" triCount to:fp
        format "- Vertices: `%`\n" vertexCount to:fp
        format "- Materials: `%`\n" mats.count to:fp
        format "- Bounds min: `%`\n" mn to:fp
        format "- Bounds max: `%`\n" mx to:fp
        format "- Bounds size: `%`\n" size to:fp
        format "- Width / height ratio: `%`\n" widthHeightRatio to:fp
        format "- Bone-like nodes: `%`\n" bones.count to:fp
        format "- Has Skin: `%`\n" (skinObjects.count > 0) to:fp
        format "- Max influence per vertex: `%`\n" maxInfluences to:fp
        format "\n## Issues\n\n" to:fp
        if issues.count == 0 then
        (
            format "- None\n" to:fp
        )
        else
        (
            for issue in issues do format "- %\n" issue to:fp
        )
        format "\n## Output\n\n" to:fp
        format "- JSON: `%`\n" jsonPath to:fp
        close fp

        #(jsonPath, mdPath, issues.count)
    )
)

AIRA_AssetQC = AIRAAssetQCTool()
