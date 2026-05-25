/*
Batch test for AIRA Stage01 with one FBX file.

Default target comes from AIRA_STAGE01_FBX_PATH or config/sourceRoot.

Run:
server\batch_stage01_fbx.ps1 -SourceFbx "<path-to-model.fbx>" -AssetName "<asset-name>"
*/

global AIRA_STAGE01_HEADLESS = true
global AIRA_Stage01
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

fn writeLine fp text =
(
    format "%\n" text to:fp
)

fn nodeClassName n =
(
    try((classOf n) as string)catch("unknown")
)

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

fn texturedScreenshotDir outDir assetName =
(
    local root = outDir + @"\textured_screenshots"
    local dir = root + @"\" + assetName
    ensureDir root
    ensureDir dir
    dir
)

fn prepareTextureDisplay =
(
    try
    (
        for m in scenematerials do
        (
            try(showTextureMap m true)catch()
        )
    )
    catch()
)

fn renderTexturedView outDir assetName viewName bounds =
(
    local dir = texturedScreenshotDir outDir assetName
    local path = dir + @"\" + assetName + @"_textured_" + viewName + @".png"
    local mn = bounds[1]
    local mx = bounds[2]
    local center = (mn + mx) / 2.0
    local size = mx - mn
    local span = abs size.x
    if (abs size.y) > span do span = abs size.y
    if (abs size.z) > span do span = abs size.z
    if span < 1.0 do span = 1.0
    local distance = span * 2.8
    local camPos = [center.x, center.y - distance, center.z]
    if viewName == "side" do camPos = [center.x + distance, center.y, center.z]
    if viewName == "top" do camPos = [center.x, center.y, center.z + distance]

    local targetNode = undefined
    local cam = undefined
    local keyLight = undefined
    local fillLight = undefined
    local ok = false
    try
    (
        targetNode = Targetobject name:("AIRA_TEXTURE_TARGET_" + viewName) pos:center
        cam = Targetcamera name:("AIRA_TEXTURE_CAMERA_" + viewName) pos:camPos target:targetNode
        try(cam.orthoProjection = true)catch()
        try(cam.orthoWidth = span * 1.25)catch()
        keyLight = OmniLight name:("AIRA_TEXTURE_KEY_" + viewName) pos:(camPos + [0, 0, span * 0.35])
        fillLight = OmniLight name:("AIRA_TEXTURE_FILL_" + viewName) pos:(center + [0, -distance * 0.45, span * 0.65])
        try(keyLight.multiplier = 0.85)catch()
        try(fillLight.multiplier = 0.35)catch()
        render camera:cam outputfile:path vfb:false width:1200 height:900
        ok = doesFileExist path
    )
    catch
    (
        format "[AIRA Batch] Textured render failed for %: %\n" viewName (getCurrentException())
        ok = false
    )
    try(if keyLight != undefined do delete keyLight)catch()
    try(if fillLight != undefined do delete fillLight)catch()
    try(if cam != undefined do delete cam)catch()
    try(if targetNode != undefined do delete targetNode)catch()
    #(ok, path)
)

fn renderTexturedScreenshots outDir assetName =
(
    prepareTextureDisplay()
    local nodes = for n in geometry collect n
    local bounds = undefined
    try(bounds = nodeGetBoundingBox nodes[1] nodes[1].transform)catch(bounds = undefined)
    if nodes.count > 0 do
    (
        local mn = [1e9, 1e9, 1e9]
        local mx = [-1e9, -1e9, -1e9]
        for n in nodes do
        (
            try
            (
                local b = nodeGetBoundingBox n n.transform
                if b[1].x < mn.x do mn.x = b[1].x
                if b[1].y < mn.y do mn.y = b[1].y
                if b[1].z < mn.z do mn.z = b[1].z
                if b[2].x > mx.x do mx.x = b[2].x
                if b[2].y > mx.y do mx.y = b[2].y
                if b[2].z > mx.z do mx.z = b[2].z
            )
            catch()
        )
        bounds = #(mn, mx)
    )
    if bounds == undefined then #(0, #())
    else
    (
        local outputs = #()
        local count = 0
        for viewName in #("front", "side", "top") do
        (
            local result = renderTexturedView outDir assetName viewName bounds
            append outputs result[2]
            if result[1] do count += 1
        )
        #(count, outputs)
    )
)

fn wireBoneScreenshotDir outDir assetName =
(
    local root = outDir + @"\wire_bone_screenshots"
    local dir = root + @"\" + assetName
    ensureDir root
    ensureDir dir
    dir
)

fn modelRenderNodes =
(
    for n in geometry where not (matchPattern n.name pattern:"AIRA_*" ignoreCase:true) collect n
)

fn makeSelfLitMaterial matName diffuseColor =
(
    local m = StandardMaterial name:matName
    try(m.diffuse = diffuseColor)catch()
    try(m.selfIllumAmount = 100)catch()
    try(m.twoSided = true)catch()
    m
)

fn applyWireMaterial nodes =
(
    local saved = #()
    local wireMat = makeSelfLitMaterial "AIRA_TECH_WIREFRAME_MAT" (color 220 245 248)
    try(wireMat.wire = true)catch()
    try(wireMat.wireSize = 1.0)catch()
    try(wireMat.opacity = 45)catch()
    for n in nodes do
    (
        append saved #(n, n.material, n.wirecolor)
        try(n.material = wireMat)catch()
        try(n.wirecolor = (color 0 225 240))catch()
    )
    saved
)

fn restoreWireMaterial saved =
(
    for item in saved do
    (
        local n = item[1]
        if isValidNode n do
        (
            try(n.material = item[2])catch()
            try(n.wirecolor = item[3])catch()
        )
    )
)

fn createBoneRenderSplines =
(
    local tempNodes = #()
    local mat = makeSelfLitMaterial "AIRA_TECH_BONE_MAT" (color 255 168 28)
    if AIRA_Stage01 != undefined do
    (
        local bipRoot = AIRA_Stage01.findBipedRoot()
        local segments = AIRA_Stage01.bipedSnapshotSegments()
        for seg in segments do
        (
            local startNode = AIRA_Stage01.bipedNodeForGuide bipRoot seg[1]
            local endNode = AIRA_Stage01.bipedNodeForGuide bipRoot seg[2]
            local startPos = if startNode != undefined then AIRA_Stage01.getBipedNodePosition startNode else undefined
            local endPos = if endNode != undefined then AIRA_Stage01.getBipedNodePosition endNode else undefined
            if (startPos != undefined and endPos != undefined) do
            (
                local shape = splineShape name:("AIRA_RENDER_BONE_" + seg[1] + "_" + seg[2])
                try(addNewSpline shape)catch()
                try(addKnot shape 1 #corner #line startPos)catch()
                try(addKnot shape 1 #corner #line endPos)catch()
                try(updateShape shape)catch()
                local thickness = 1.0
                try(thickness = (AIRA_Stage01.templateBoneThickness seg[1] seg[2] (distance startPos endPos)) * 0.28)catch(thickness = 1.0)
                if thickness < 0.45 do thickness = 0.45
                if thickness > 5.0 do thickness = 5.0
                try(shape.render_renderable = true)catch()
                try(shape.render_displayRenderMesh = true)catch()
                try(shape.render_thickness = thickness)catch()
                try(shape.render_sides = 8)catch()
                try(shape.material = mat)catch()
                try(shape.wirecolor = (color 255 168 28))catch()
                append tempNodes shape
            )
        )
    )
    tempNodes
)

fn createGuideRenderMarkers =
(
    local tempNodes = #()
    if AIRA_Stage01 != undefined do
    (
        local mat = makeSelfLitMaterial "AIRA_TECH_GUIDE_MAT" (color 255 230 70)
        local names = AIRA_Stage01.requiredGuideNames()
        for name in names do
        (
            local g = AIRA_Stage01.getGuide name
            if g != undefined do
            (
                local radius = 0.75
                if name == "Root" do radius = 0.45
                if name == "CrestTop" do radius = 0.55
                local s = sphere name:("AIRA_RENDER_GUIDE_" + name) radius:radius segments:8 pos:g.pos
                try(s.material = mat)catch()
                try(s.wirecolor = (color 255 230 70))catch()
                append tempNodes s
            )
        )
    )
    tempNodes
)

fn renderWireBoneView outDir assetName viewName bounds =
(
    local dir = wireBoneScreenshotDir outDir assetName
    local path = dir + @"\" + assetName + @"_wire_bone_" + viewName + @".png"
    local mn = bounds[1]
    local mx = bounds[2]
    local center = (mn + mx) / 2.0
    local size = mx - mn
    local span = abs size.x
    if (abs size.y) > span do span = abs size.y
    if (abs size.z) > span do span = abs size.z
    if span < 1.0 do span = 1.0
    local distance = span * 2.8
    local camPos = [center.x, center.y - distance, center.z]
    if viewName == "side" do camPos = [center.x + distance, center.y, center.z]
    if viewName == "top" do camPos = [center.x, center.y, center.z + distance]

    local targetNode = undefined
    local cam = undefined
    local keyLight = undefined
    local ok = false
    try
    (
        targetNode = Targetobject name:("AIRA_WIRE_TARGET_" + viewName) pos:center
        cam = Targetcamera name:("AIRA_WIRE_CAMERA_" + viewName) pos:camPos target:targetNode
        try(cam.orthoProjection = true)catch()
        try(cam.orthoWidth = span * 1.25)catch()
        keyLight = OmniLight name:("AIRA_WIRE_KEY_" + viewName) pos:(camPos + [0, 0, span * 0.35])
        try(keyLight.multiplier = 0.70)catch()
        render camera:cam outputfile:path vfb:false width:1200 height:900
        ok = doesFileExist path
    )
    catch
    (
        format "[AIRA Batch] Wire/bone render failed for %: %\n" viewName (getCurrentException())
        ok = false
    )
    try(if keyLight != undefined do delete keyLight)catch()
    try(if cam != undefined do delete cam)catch()
    try(if targetNode != undefined do delete targetNode)catch()
    #(ok, path)
)

fn renderWireBoneScreenshots outDir assetName =
(
    local nodes = modelRenderNodes()
    local bounds = undefined
    if nodes.count > 0 do
    (
        local mn = [1e9, 1e9, 1e9]
        local mx = [-1e9, -1e9, -1e9]
        for n in nodes do
        (
            try
            (
                local b = nodeGetBoundingBox n n.transform
                if b[1].x < mn.x do mn.x = b[1].x
                if b[1].y < mn.y do mn.y = b[1].y
                if b[1].z < mn.z do mn.z = b[1].z
                if b[2].x > mx.x do mx.x = b[2].x
                if b[2].y > mx.y do mx.y = b[2].y
                if b[2].z > mx.z do mx.z = b[2].z
            )
            catch()
        )
        bounds = #(mn, mx)
    )
    if bounds == undefined then #(0, #())
    else
    (
        local savedMaterials = applyWireMaterial nodes
        local tempBones = createBoneRenderSplines()
        local tempGuides = createGuideRenderMarkers()
        local outputs = #()
        local count = 0
        for viewName in #("front", "side", "top") do
        (
            local result = renderWireBoneView outDir assetName viewName bounds
            append outputs result[2]
            if result[1] do count += 1
        )
        restoreWireMaterial savedMaterials
        for n in tempBones do try(if isValidNode n do delete n)catch()
        for n in tempGuides do try(if isValidNode n do delete n)catch()
        #(count, outputs)
    )
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
            format "[AIRA Batch] FBX import completed with importer warning: %\n" exceptionMessage
        else
            format "[AIRA Batch] FBX import failed: %\n" exceptionMessage
    )

    afterCount > beforeCount
)

fn main =
(
    local toolRoot = getEnv "AIRA_TOOL_ROOT" "."
    local outDir = getEnv "AIRA_STAGE01_OUT_DIR" (getEnv "AIRA_OUT_DIR" (joinPath toolRoot "out"))
    local sourceRoot = getEnv "AIRA_SOURCE_ROOT" (joinPath toolRoot "source")
    local asciiFbxPath = joinPath outDir "luxun_model.fbx"
    local fallbackFbxPath = joinPath sourceRoot @"luxun_model\陆逊模型.fbx"
    local fbxPath = getEnv "AIRA_STAGE01_FBX_PATH" (if doesFileExist asciiFbxPath then asciiFbxPath else fallbackFbxPath)
    local assetName = getEnv "AIRA_STAGE01_ASSET_NAME" (getFilenameFile fbxPath)
    local guideAlgorithm = getEnv "AIRA_STAGE01_GUIDE_ALGO" "tutorial_centerline_qbird"
    local maxFitIterations = (getEnv "AIRA_STAGE01_MAX_FIT_ITERATIONS" "18") as integer
    local toolPath = joinPath (joinPath toolRoot "maxscript") "aira_stage01_biped.ms"
    local assetQcPath = joinPath (joinPath toolRoot "maxscript") "aira_asset_qc.ms"
    local reportPath = outDir + @"\" + assetName + @"_stage01_batch_summary.md"
    local scenePath = outDir + @"\" + assetName + @"_stage01_rig_scene.max"

    ensureDir outDir
    resetMaxFile #noPrompt

    local fp = createFile reportPath
    writeLine fp "# Luxun FBX Stage01 Batch Test"
    writeLine fp ""
    writeLine fp ("- FBX: `" + fbxPath + "`")
    writeLine fp ("- Guide algorithm: `" + guideAlgorithm + "`")
    writeLine fp ("- Max CT refinement iterations: `" + (maxFitIterations as string) + "`")
    writeLine fp ("- Started: `" + (localTime as string) + "`")

    if not (doesFileExist fbxPath) then
    (
        writeLine fp "- Import: `failed, FBX file does not exist`"
        close fp
        quitMAX #noPrompt
        return false
    )

    local importOk = safeImportFbx fbxPath
    local textureRelink = relinkBitmapsToLocalSidecar fbxPath assetName "AIRA_STAGE01_TEXTURE_DIR"

    local geoNodes = for n in geometry collect n
    local shapeNodes = for n in shapes collect n
    local helperNodes = for n in helpers collect n
    local boneNodes = for n in objects where (matchPattern (nodeClassName n) pattern:"*Bone*" ignoreCase:true) collect n
    if geoNodes.count > 0 do importOk = true

    writeLine fp ("- Import OK: `" + (importOk as string) + "`")
    writeLine fp ("- Texture bitmap relinked: `" + (textureRelink[1] as string) + "`")
    writeLine fp ("- Texture bitmap unresolved: `" + (textureRelink[2] as string) + "`")
    writeLine fp ("- Texture search dirs: `" + (textureRelink[3] as string) + "`")

    writeLine fp ("- Geometry nodes: `" + (geoNodes.count as string) + "`")
    writeLine fp ("- Shape nodes: `" + (shapeNodes.count as string) + "`")
    writeLine fp ("- Helper nodes: `" + (helperNodes.count as string) + "`")
    writeLine fp ("- Bone-like nodes: `" + (boneNodes.count as string) + "`")
    writeLine fp ("- Approx triangle faces: `" + ((countTriFaces geoNodes) as string) + "`")

    writeLine fp ""
    writeLine fp "## Imported Geometry"
    writeLine fp ""
    for n in geoNodes do
    (
        writeLine fp ("- `" + n.name + "` class `" + (nodeClassName n) + "`")
    )

    if geoNodes.count > 0 then
    (
        select geoNodes
        fileIn toolPath
        AIRA_Stage01.guideAlgorithm = guideAlgorithm
        saveMaxFile scenePath

        local bodyProfile = AIRA_Stage01.writeBodyProfileReport assetName
        local guideCount = AIRA_Stage01.createGuidesFromSelection()
        local mirrorCount = AIRA_Stage01.mirrorLeftGuidesToRight()
        local bip = AIRA_Stage01.createBipedFromGuides()
        local refineResult = AIRA_Stage01.refineBipedToGuides maxFitIterations
        local bipedName = if bip != undefined then bip.name else ""

        saveMaxFile scenePath
        local stageReport = AIRA_Stage01.generateReport()
        local fitQc = AIRA_Stage01.generateFitQualityReport assetName
        AIRA_Stage01.deleteTemplateSkeleton()
        local visualSnapshot = AIRA_Stage01.writeVisualSnapshotReport assetName

        fileIn assetQcPath
        local rigAssetQc = AIRA_AssetQC.writeReports (assetName + "_stage01_rig")
        local texturedShots = renderTexturedScreenshots outDir assetName
        local wireBoneShots = renderWireBoneScreenshots outDir assetName
        saveMaxFile scenePath

        writeLine fp ""
        writeLine fp "## Stage01 Result"
        writeLine fp ""
        writeLine fp ("- Body profile JSON: `" + bodyProfile[1] + "`")
        writeLine fp ("- Body profile Markdown: `" + bodyProfile[2] + "`")
        writeLine fp ("- Body profile type: `" + bodyProfile[3] + "`")
        writeLine fp ("- Guides created: `" + (guideCount as string) + "`")
        writeLine fp ("- Guide pairs mirrored: `" + (mirrorCount as string) + "`")
        writeLine fp ("- Biped root: `" + bipedName + "`")
        writeLine fp ("- CT refinement converged: `" + (refineResult[1] as string) + "`")
        writeLine fp ("- CT refinement iterations: `" + (refineResult[2] as string) + "`")
        writeLine fp ("- CT refinement failures: `" + (refineResult[3] as string) + " -> " + (refineResult[4] as string) + "`")
        writeLine fp ("- CT refinement max offset: `" + (refineResult[5] as string) + " -> " + (refineResult[6] as string) + "`")
        writeLine fp ("- Stage report: `" + stageReport + "`")
        writeLine fp ("- Fit QC JSON: `" + fitQc[1] + "`")
        writeLine fp ("- Fit QC Markdown: `" + fitQc[2] + "`")
        writeLine fp "- Fit QC legacy rating fields: `hidden_diagnostic_only`"
        writeLine fp ("- Fit QC production ready: `" + (fitQc[4] as string) + "`")
        writeLine fp "- Skeleton policy: `biped_only_no_template_bones`"
        writeLine fp ("- Visual snapshot JSON: `" + visualSnapshot[1] + "`")
        writeLine fp ("- Visual snapshot sampled points: `" + (visualSnapshot[2] as string) + "`")
        writeLine fp ("- Rig asset QC JSON: `" + rigAssetQc[1] + "`")
        writeLine fp ("- Rig asset QC Markdown: `" + rigAssetQc[2] + "`")
        writeLine fp ("- Textured screenshots generated: `" + (texturedShots[1] as string) + "`")
        for shotPath in texturedShots[2] do writeLine fp ("  - `" + shotPath + "`")
        writeLine fp ("- Wire/bone screenshots generated: `" + (wireBoneShots[1] as string) + "`")
        for shotPath in wireBoneShots[2] do writeLine fp ("  - `" + shotPath + "`")
        writeLine fp ("- Saved scene: `" + scenePath + "`")
    )
    else
    (
        writeLine fp ""
        writeLine fp "## Stage01 Result"
        writeLine fp ""
        writeLine fp "- Skipped: no geometry nodes imported."
    )

    writeLine fp ""
    writeLine fp ("- Finished: `" + (localTime as string) + "`")
    close fp
    format "[AIRA Batch] Summary: %\n" reportPath
    quitMAX #noPrompt
    true
)

main()
