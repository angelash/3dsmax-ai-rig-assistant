/*
Batch runner for AIRA Stage02 deformation smoke tests.

Environment:
- AIRA_STAGE02_DEFORM_SOURCE_MAX
- AIRA_STAGE02_ASSET_NAME
- AIRA_STAGE02_DEFORM_OUT_DIR
*/

global AIRA_STAGE02_HEADLESS = true
global AIRA_Stage02

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

fn jsonEscape value =
(
    local s = value as string
    s = substituteString s "\\" "\\\\"
    s = substituteString s "\"" "\\\""
    s = substituteString s "\r" "\\r"
    s = substituteString s "\n" "\\n"
    s = substituteString s "\t" "\\t"
    s
)

fn jsonString value =
(
    "\"" + jsonEscape value + "\""
)

fn jsonBool value =
(
    if value then "true" else "false"
)

fn jsonNumber value =
(
    formattedPrint value format:".6f"
)

fn jsonPoint p =
(
    "[" + jsonNumber p.x + "," + jsonNumber p.y + "," + jsonNumber p.z + "]"
)

fn writeLine fp text =
(
    format "%\n" text to:fp
)

fn minPoint a b =
(
    [(if a.x < b.x then a.x else b.x), (if a.y < b.y then a.y else b.y), (if a.z < b.z then a.z else b.z)]
)

fn maxPoint a b =
(
    [(if a.x > b.x then a.x else b.x), (if a.y > b.y then a.y else b.y), (if a.z > b.z then a.z else b.z)]
)

fn pointValid p =
(
    local ok = true
    try
    (
        ok = (p.x == p.x) and (p.y == p.y) and (p.z == p.z)
        ok = ok and (abs p.x < 1000000.0) and (abs p.y < 1000000.0) and (abs p.z < 1000000.0)
    )
    catch(ok = false)
    ok
)

fn modelNodes =
(
    local out = #()
    if AIRA_Stage02 != undefined then
    (
        out = AIRA_Stage02.geometryNodes()
    )
    else
    (
        out = for n in geometry where not (matchPattern n.name pattern:"AIRA_*" ignoreCase:true) collect n
    )
    out
)

fn modelBounds nodes =
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
)

fn collectSnapshotVertices nodes =
(
    local vertices = #()
    for n in nodes do
    (
        local tri = undefined
        try(tri = snapshotAsMesh n)catch(tri = undefined)
        if tri != undefined do
        (
            for v = 1 to tri.numverts do
            (
                append vertices ((getVert tri v) * n.objectTransform)
            )
            try(delete tri)catch()
        )
    )
    vertices
)

fn compareVertices base pose =
(
    local count = if base.count < pose.count then base.count else pose.count
    local moved = 0
    local invalid = 0
    local maxDisp = 0.0
    local totalDisp = 0.0
    for i = 1 to count do
    (
        if (not pointValid pose[i]) then
        (
            invalid += 1
        )
        else
        (
            local d = distance base[i] pose[i]
            totalDisp += d
            if d > maxDisp do maxDisp = d
            if d > 0.01 do moved += 1
        )
    )
    #(count, moved, invalid, (if count > 0 then totalDisp / count else 0.0), maxDisp)
)

fn setFigureModeOff bipRoot =
(
    local ok = true
    try(bipRoot.controller.figureMode = false)catch(ok = false)
    ok
)

fn semanticNode semanticNodes semanticName =
(
    for item in semanticNodes do
    (
        if item[1] == semanticName do return item[2]
    )
    undefined
)

fn rotateSemantic semanticNodes semanticName axis degrees =
(
    local node = semanticNode semanticNodes semanticName
    local ok = false
    if node != undefined do
    (
        local currentRot = undefined
        try(currentRot = biped.getTransform node #rotation)catch(currentRot = undefined)
        if currentRot != undefined do
        (
            local q = angleaxis degrees axis
            try
            (
                biped.setTransform node #rotation (q * currentRot) false
                ok = true
            )
            catch
            (
                try
                (
                    biped.setTransform node #rotation (currentRot * q) false
                    ok = true
                )
                catch(ok = false)
            )
        )
    )
    ok
)

fn applyPose semanticNodes poseId =
(
    local actions = #()
    if poseId == "head_turn" do
    (
        append actions #("Neck", [0, 0, 1], 10.0)
        append actions #("Head", [0, 0, 1], 16.0)
    )
    if poseId == "left_arm_raise" do
    (
        append actions #("L_Clavicle", [0, 0, 1], 8.0)
        append actions #("L_UpperArm", [0, 1, 0], -32.0)
        append actions #("L_Forearm", [0, 1, 0], -12.0)
    )
    if poseId == "right_elbow_bend" do
    (
        append actions #("R_UpperArm", [0, 1, 0], 10.0)
        append actions #("R_Forearm", [0, 1, 0], 38.0)
        append actions #("R_Hand", [1, 0, 0], 8.0)
    )
    if poseId == "left_knee_bend" do
    (
        append actions #("L_Thigh", [1, 0, 0], 10.0)
        append actions #("L_Calf", [1, 0, 0], -34.0)
        append actions #("L_Foot", [1, 0, 0], 14.0)
    )
    if poseId == "right_foot_roll" do
    (
        append actions #("R_Calf", [1, 0, 0], -12.0)
        append actions #("R_Foot", [1, 0, 0], 24.0)
        append actions #("R_Toe", [1, 0, 0], 12.0)
    )
    if poseId == "torso_twist" do
    (
        append actions #("Spine", [0, 0, 1], 8.0)
        append actions #("Chest", [0, 0, 1], 14.0)
    )

    local attempted = actions.count
    local applied = 0
    for action in actions do
    (
        if rotateSemantic semanticNodes action[1] action[2] action[3] do applied += 1
    )
    #(attempted, applied)
)

fn makeSelfLitMaterial matName diffuseColor =
(
    local m = StandardMaterial name:matName
    try(m.diffuse = diffuseColor)catch()
    try(m.selfIllumAmount = 100)catch()
    try(m.twoSided = true)catch()
    m
)

fn preparePoseMaterials nodes =
(
    local saved = #()
    local mat = makeSelfLitMaterial "AIRA_DEFORM_TEST_MAT" (color 210 224 236)
    try(mat.wire = false)catch()
    for n in nodes do
    (
        append saved #(n, n.material, n.wirecolor)
        try(n.material = mat)catch()
        try(n.wirecolor = (color 90 170 220))catch()
    )
    saved
)

fn restorePoseMaterials saved =
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

fn renderPoseView screenshotDir assetName poseId viewName bounds =
(
    local path = joinPath screenshotDir (assetName + "_" + poseId + "_" + viewName + ".png")
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
        targetNode = Targetobject name:("AIRA_DEFORM_TARGET_" + poseId + "_" + viewName) pos:center
        cam = Targetcamera name:("AIRA_DEFORM_CAMERA_" + poseId + "_" + viewName) pos:camPos target:targetNode
        try(cam.orthoProjection = true)catch()
        try(cam.orthoWidth = span * 1.30)catch()
        keyLight = OmniLight name:("AIRA_DEFORM_KEY_" + poseId + "_" + viewName) pos:(camPos + [0, 0, span * 0.35])
        fillLight = OmniLight name:("AIRA_DEFORM_FILL_" + poseId + "_" + viewName) pos:(center + [0, -distance * 0.45, span * 0.65])
        try(keyLight.multiplier = 0.70)catch()
        try(fillLight.multiplier = 0.30)catch()
        render camera:cam outputfile:path vfb:false width:1200 height:900
        ok = doesFileExist path
    )
    catch
    (
        format "[AIRA Stage02 Deform] Render failed for %/%: %\n" poseId viewName (getCurrentException())
        ok = false
    )
    try(if keyLight != undefined do delete keyLight)catch()
    try(if fillLight != undefined do delete fillLight)catch()
    try(if cam != undefined do delete cam)catch()
    try(if targetNode != undefined do delete targetNode)catch()
    #(ok, path)
)

fn runPose sourceMax assetName outDir poseId =
(
    resetMaxFile #noPrompt
    local loadOk = true
    try(loadMaxFile sourceMax quiet:true)catch(loadOk = false)
    local toolRoot = getEnv "AIRA_TOOL_ROOT" "."
    fileIn (joinPath (joinPath toolRoot "maxscript") "aira_stage02_skin.ms")
    local nodes = modelNodes()
    local baseVerts = collectSnapshotVertices nodes
    local baseBounds = modelBounds nodes
    local bipRoot = AIRA_Stage02.findBipedRoot()
    local semanticNodes = if bipRoot != undefined then AIRA_Stage02.semanticBipedNodes bipRoot else #()
    if bipRoot != undefined do setFigureModeOff bipRoot
    sliderTime = 0f

    local poseResult = if poseId == "bind" then #(0, 0) else applyPose semanticNodes poseId
    completeRedraw()
    local poseNodes = modelNodes()
    local poseVerts = collectSnapshotVertices poseNodes
    local poseBounds = modelBounds poseNodes
    local cmp = compareVertices baseVerts poseVerts
    local screenshots = #()
    local screenshotOk = 0
    local screenshotDir = joinPath outDir "screenshots"
    ensureDir screenshotDir
    local savedMaterials = preparePoseMaterials poseNodes
    local renderBounds = if poseBounds != undefined then poseBounds else baseBounds
    if renderBounds != undefined do
    (
        for viewName in #("front", "side", "top") do
        (
            local shot = renderPoseView screenshotDir assetName poseId viewName renderBounds
            append screenshots shot[2]
            if shot[1] do screenshotOk += 1
        )
    )
    restorePoseMaterials savedMaterials

    local poseSceneDir = joinPath outDir "posed_scenes"
    ensureDir poseSceneDir
    local poseScene = joinPath poseSceneDir (assetName + "_" + poseId + ".max")
    try(saveMaxFile poseScene)catch(poseScene = "")

    local issue = ""
    if not loadOk then issue = "source_load_failed"
    else if bipRoot == undefined then issue = "biped_root_missing"
    else if poseId != "bind" and poseResult[2] == 0 then issue = "pose_actions_not_applied"
    else if cmp[1] == 0 then issue = "no_vertices_checked"
    else if cmp[3] > 0 then issue = "invalid_deformed_vertices"
    else if poseId != "bind" and cmp[2] == 0 then issue = "pose_produced_no_vertex_motion"
    else if baseBounds != undefined and cmp[5] > ((baseBounds[2].z - baseBounds[1].z) * 1.2) then issue = "excessive_vertex_displacement"

    #(poseId, loadOk, (bipRoot != undefined), semanticNodes.count, poseResult[1], poseResult[2], cmp[1], cmp[2], cmp[3], cmp[4], cmp[5], screenshotOk, screenshots, poseScene, issue)
)

fn writeReports assetName sourceMax outDir results =
(
    local reportsDir = joinPath outDir "reports"
    local dataDir = joinPath outDir "data"
    ensureDir reportsDir
    ensureDir dataDir
    local jsonPath = joinPath dataDir (assetName + "_stage02_deform_test_report.json")
    local mdPath = joinPath reportsDir (assetName + "_stage02_deform_test_report.md")
    local issueCount = 0
    local poseCount = results.count
    local screenshotCount = 0
    for item in results do
    (
        if item[15] != "" do issueCount += 1
        screenshotCount += item[12]
    )

    local fp = createFile jsonPath
    format "{\n" to:fp
    format "  \"assetName\": %, \n" (jsonString assetName) to:fp
    format "  \"sourceScene\": %, \n" (jsonString sourceMax) to:fp
    format "  \"generatedAt\": %, \n" (jsonString (localTime as string)) to:fp
    format "  \"stage\": %, \n" (jsonString "stage02_deformation_smoke_test") to:fp
    format "  \"productionReady\": false,\n" to:fp
    format "  \"deformationTestComplete\": false,\n" to:fp
    format "  \"poseCount\": %, \n" poseCount to:fp
    format "  \"screenshotCount\": %, \n" screenshotCount to:fp
    format "  \"issueCount\": %, \n" issueCount to:fp
    format "  \"poses\": [\n" to:fp
    for i = 1 to results.count do
    (
        local item = results[i]
        format "    {\"poseId\": %, \"sourceLoaded\": %, \"bipedFound\": %, \"semanticNodeCount\": %, \"poseActionsAttempted\": %, \"poseActionsApplied\": %, \"verticesChecked\": %, \"movedVertices\": %, \"invalidVertices\": %, \"avgDisplacement\": %, \"maxDisplacement\": %, \"screenshotsRendered\": %, \"poseScene\": %, \"issue\": %, \"screenshots\": [" \
            (jsonString item[1]) (jsonBool item[2]) (jsonBool item[3]) item[4] item[5] item[6] item[7] item[8] item[9] (jsonNumber item[10]) (jsonNumber item[11]) item[12] (jsonString item[14]) (jsonString item[15]) to:fp
        for s = 1 to item[13].count do
        (
            format "%" (jsonString item[13][s]) to:fp
            if s < item[13].count do format ", " to:fp
        )
        format "]}" to:fp
        if i < results.count then format ",\n" to:fp else format "\n" to:fp
    )
    format "  ]\n" to:fp
    format "}\n" to:fp
    close fp

    fp = createFile mdPath
    format "# Stage02 Deformation Smoke Test: %\n\n" assetName to:fp
    format "- Source scene: `%`\n" sourceMax to:fp
    format "- Generated: `%`\n" localTime to:fp
    format "- Poses tested: `%`\n" poseCount to:fp
    format "- Screenshots rendered: `%`\n" screenshotCount to:fp
    format "- Issue count: `%`\n" issueCount to:fp
    format "- Production ready: `false`\n" to:fp
    format "- Deformation test complete: `false`\n" to:fp
    format "\n## Pose Results\n\n" to:fp
    for item in results do
    (
        format "- `%`: actions=`%/%`, vertices=`%`, moved=`%`, invalid=`%`, avgDisp=`%`, maxDisp=`%`, screenshots=`%`, issue=`%`\n" \
            item[1] item[6] item[5] item[7] item[8] item[9] (jsonNumber item[10]) (jsonNumber item[11]) item[12] (if item[15] == "" then "none" else item[15]) to:fp
    )
    format "\n## Evidence\n\n" to:fp
    for item in results do
    (
        format "### %\n\n" item[1] to:fp
        format "- Posed scene: `%`\n" item[14] to:fp
        for shot in item[13] do format "- `%`\n" shot to:fp
        format "\n" to:fp
    )
    format "## Notes\n\n" to:fp
    format "- This is an automated smoke test. It detects basic Skin response, invalid vertices, extreme displacement and produces view evidence.\n" to:fp
    format "- It does not replace tutorial-style human review of shoulders, elbows, wrists, hips, knees, ankles, feet, head/neck and accessory behavior.\n" to:fp
    format "- `deformationTestComplete=false` remains until the screenshot evidence is reviewed and accepted.\n" to:fp
    close fp

    #(jsonPath, mdPath, issueCount, screenshotCount)
)

fn main =
(
    local toolRoot = getEnv "AIRA_TOOL_ROOT" "."
    local sourceMax = getEnv "AIRA_STAGE02_DEFORM_SOURCE_MAX" ""
    local assetName = getEnv "AIRA_STAGE02_ASSET_NAME" "stage02_asset"
    local outDir = getEnv "AIRA_STAGE02_DEFORM_OUT_DIR" (joinPath (getEnv "AIRA_OUT_DIR" (joinPath toolRoot "out")) "stage02_deform_current")
    local reportsDir = joinPath outDir "reports"
    local logsDir = joinPath outDir "logs"
    ensureDir outDir
    ensureDir reportsDir
    ensureDir logsDir
    local summaryPath = joinPath reportsDir (assetName + "_stage02_deform_batch_summary.md")
    local fp = createFile summaryPath
    writeLine fp ("# Stage02 Deformation Batch: " + assetName)
    writeLine fp ""
    writeLine fp ("- Source scene: `" + sourceMax + "`")
    writeLine fp ("- Started: `" + (localTime as string) + "`")

    if sourceMax == "" or not (doesFileExist sourceMax) then
    (
        writeLine fp "- Source scene: `missing`"
        close fp
        quitMAX #noPrompt
        return false
    )

    local poseIds = #("bind", "head_turn", "left_arm_raise", "right_elbow_bend", "left_knee_bend", "right_foot_roll", "torso_twist")
    local results = #()
    for poseId in poseIds do
    (
        local result = runPose sourceMax assetName outDir poseId
        append results result
        writeLine fp ("- Pose `" + poseId + "`: movedVertices=`" + (result[8] as string) + "`, maxDisp=`" + (formattedPrint result[11] format:".4f") + "`, issue=`" + (if result[15] == "" then "none" else result[15]) + "`")
    )

    local reports = writeReports assetName sourceMax outDir results
    writeLine fp ("- Report JSON: `" + reports[1] + "`")
    writeLine fp ("- Report Markdown: `" + reports[2] + "`")
    writeLine fp ("- Issue count: `" + (reports[3] as string) + "`")
    writeLine fp ("- Screenshots rendered: `" + (reports[4] as string) + "`")
    writeLine fp ("- Finished: `" + (localTime as string) + "`")
    close fp
    format "[AIRA Stage02 Deform Batch] Summary: %\n" summaryPath
    quitMAX #noPrompt
    true
)

main()
