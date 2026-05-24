/*
AI Rig Assistant - Stage 02 Skin Setup Tool
Target: 3ds Max 2020+ / MAXScript

This script is intentionally independent from Stage01. It consumes an existing
Stage01-style Biped scene, adds Skin to character geometry, adds deforming
Biped nodes to Skin, creates a first-pass tutorial-style weight assignment, and
writes JSON/Markdown reports. It does not create or refit guides/Biped nodes.
*/

global AIRA_Stage02
global AIRA_Stage02_UI
global AIRA_STAGE02_HEADLESS

struct AIRAStage02SkinTool
(
    prefix = "AIRA",
    bipedName = "AIRA_Biped_COM",
    outDir = @"F:\workspace\github\3dsmax-ai-rig-assistant\out\stage02_current_scene",
    boneAffectLimit = 3,
    maxAssignedInfluences = 3,
    epsilon = 0.00001,

    fn log msg =
    (
        format "[AIRA Stage02] %\n" msg
    ),

    fn ensureDir path =
    (
        if not (doesDirectoryExist path) do makeDir path all:true
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

    fn getEnv key defaultValue =
    (
        local value = (dotNetClass "System.Environment").GetEnvironmentVariable key
        if value == undefined or value == "" then defaultValue else value
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

    fn minPoint a b =
    (
        [(if a.x < b.x then a.x else b.x), (if a.y < b.y then a.y else b.y), (if a.z < b.z then a.z else b.z)]
    ),

    fn maxPoint a b =
    (
        [(if a.x > b.x then a.x else b.x), (if a.y > b.y then a.y else b.y), (if a.z > b.z then a.z else b.z)]
    ),

    fn nodeClassName n =
    (
        try((classOf n) as string)catch("unknown")
    ),

    fn controllerClassName n =
    (
        try((classOf n.controller) as string)catch("unknown")
    ),

    fn isBipedLikeNode n =
    (
        if not (isValidNode n) then false
        else
        (
            local cls = nodeClassName n
            local ctrlCls = controllerClassName n
            local hasFigure = false
            try(hasFigure = isProperty n.controller #figureMode)catch(hasFigure = false)
            hasFigure or \
            (matchPattern n.name pattern:(bipedName + "*") ignoreCase:true) or \
            (matchPattern n.name pattern:"Bip*" ignoreCase:true) or \
            (matchPattern cls pattern:"*Biped*" ignoreCase:true) or \
            (matchPattern ctrlCls pattern:"*Bip*" ignoreCase:true)
        )
    ),

    fn isRigHelperNode n =
    (
        if not (isValidNode n) then true
        else
        (
            (matchPattern n.name pattern:"AIRA_GUIDE_*" ignoreCase:true) or \
            (matchPattern n.name pattern:"AIRA_BONE_*" ignoreCase:true) or \
            (matchPattern n.name pattern:"AIRA_RENDER_*" ignoreCase:true) or \
            (matchPattern n.name pattern:"AIRA_TEXTURE_*" ignoreCase:true) or \
            (matchPattern n.name pattern:"AIRA_TECH_*" ignoreCase:true) or \
            isBipedLikeNode n
        )
    ),

    fn isCandidateModelNode n =
    (
        if not (isValidNode n) then false
        else if isRigHelperNode n then false
        else
        (
            local ok = true
            try
            (
                local mn = n.min
                local mx = n.max
            )
            catch(ok = false)
            ok
        )
    ),

    fn geometryNodes =
    (
        for n in geometry where isCandidateModelNode n collect n
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

    fn dot3 a b =
    (
        (a.x * b.x) + (a.y * b.y) + (a.z * b.z)
    ),

    fn distanceToSegment p a b =
    (
        if a == undefined then 999999.0
        else if b == undefined then distance p a
        else
        (
            local ab = b - a
            local len2 = dot3 ab ab
            if len2 < epsilon then distance p a
            else
            (
                local t = (dot3 (p - a) ab) / len2
                if t < 0.0 do t = 0.0
                if t > 1.0 do t = 1.0
                local nearest = a + (ab * t)
                distance p nearest
            )
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

    fn ensureSkinModifier obj =
    (
        local skinMod = findSkinModifier obj
        local existed = skinMod != undefined
        if skinMod == undefined do
        (
            try
            (
                skinMod = Skin()
                addModifier obj skinMod
            )
            catch
            (
                skinMod = undefined
            )
        )
        #(skinMod, existed)
    ),

    fn setSkinBoneAffectLimit skinMod =
    (
        local ok = false
        try(skinMod.bone_Limit = boneAffectLimit; ok = true)catch()
        try(skinOps.SetBoneLimit skinMod boneAffectLimit; ok = true)catch()
        try(skinMod.vertexWeightMode = 1)catch()
        ok
    ),

    fn findBipedRoot =
    (
        local fallback = undefined
        for n in objects do
        (
            local isBip = false
            try(isBip = isProperty n.controller #figureMode)catch(isBip = false)
            if isBip do
            (
                if matchPattern n.name pattern:(bipedName + "*") ignoreCase:true do return n
                if fallback == undefined do fallback = n
            )
        )
        fallback
    ),

    fn getBipedNode bipRoot limbName linkIndex =
    (
        local n = undefined
        try
        (
            if linkIndex == 0 then n = biped.getNode bipRoot limbName
            else n = biped.getNode bipRoot limbName link:linkIndex
        )
        catch(n = undefined)
        n
    ),

    fn getBipedNodePosition node =
    (
        local p = undefined
        try(p = biped.getTransform node #pos)catch(p = undefined)
        if p == undefined do try(p = node.transform.pos)catch(p = undefined)
        if p == undefined do try(p = node.pos)catch(p = undefined)
        p
    ),

    fn semanticBipedRequests =
    (
        #(
            #("Pelvis", #pelvis, 0, "torso", "C"),
            #("Spine", #spine, 1, "torso", "C"),
            #("Chest", #spine, 2, "torso", "C"),
            #("Neck", #neck, 0, "neck", "C"),
            #("Head", #head, 0, "head", "C"),

            #("L_Clavicle", #larm, 1, "clavicle", "L"),
            #("L_UpperArm", #larm, 2, "arm", "L"),
            #("L_Forearm", #larm, 3, "arm", "L"),
            #("L_Hand", #larm, 4, "hand", "L"),
            #("R_Clavicle", #rarm, 1, "clavicle", "R"),
            #("R_UpperArm", #rarm, 2, "arm", "R"),
            #("R_Forearm", #rarm, 3, "arm", "R"),
            #("R_Hand", #rarm, 4, "hand", "R"),

            #("L_Thigh", #lleg, 1, "leg", "L"),
            #("L_Calf", #lleg, 2, "leg", "L"),
            #("L_Foot", #lleg, 3, "foot", "L"),
            #("L_Toe", #ltoes, 1, "foot", "L"),
            #("R_Thigh", #rleg, 1, "leg", "R"),
            #("R_Calf", #rleg, 2, "leg", "R"),
            #("R_Foot", #rleg, 3, "foot", "R"),
            #("R_Toe", #rtoes, 1, "foot", "R")
        )
    ),

    fn semanticBipedNodes bipRoot =
    (
        local out = #()
        local names = #()
        if bipRoot != undefined do
        (
            for req in semanticBipedRequests() do
            (
                local n = getBipedNode bipRoot req[2] req[3]
                if n != undefined and (findItem names n.name) == 0 do
                (
                    append names n.name
                    append out #(req[1], n, req[4], req[5])
                )
            )
        )
        out
    ),

    fn addBipedBonesToSkin skinMod semanticNodes =
    (
        local added = 0
        local failed = #()
        for item in semanticNodes do
        (
            local n = item[2]
            try
            (
                skinOps.addBone skinMod n 1
                added += 1
            )
            catch
            (
                append failed item[1]
            )
        )
        #(added, failed)
    ),

    fn skinBoneIndexForNode skinMod node =
    (
        local count = 0
        try(count = skinOps.GetNumberBones skinMod)catch(count = 0)
        for i = 1 to count do
        (
            local boneName = ""
            try(boneName = skinOps.GetBoneName skinMod i 0)catch(boneName = "")
            if boneName == node.name do return i
            try
            (
                local boneNode = skinOps.GetBoneNode skinMod i
                if boneNode == node do return i
            )
            catch()
        )
        0
    ),

    fn semanticNode semanticNodes semanticName =
    (
        for item in semanticNodes do
        (
            if item[1] == semanticName do return item[2]
        )
        undefined
    ),

    fn semanticItem semanticNodes semanticName =
    (
        for item in semanticNodes do
        (
            if item[1] == semanticName do return item
        )
        undefined
    ),

    fn nodePos semanticNodes semanticName =
    (
        local n = semanticNode semanticNodes semanticName
        if n == undefined then undefined else getBipedNodePosition n
    ),

    fn extrapolatedEnd startPos previousPos ratio fallback =
    (
        if startPos == undefined then fallback
        else if previousPos == undefined then fallback
        else startPos + ((startPos - previousPos) * ratio)
    ),

    fn addInfluenceRef refs skinMod semanticNodes semanticName startPos endPos =
    (
        local item = semanticItem semanticNodes semanticName
        if item != undefined do
        (
            local boneIndex = skinBoneIndexForNode skinMod item[2]
            if boneIndex > 0 do append refs #(semanticName, boneIndex, item[3], item[4], startPos, endPos)
        )
    ),

    fn buildInfluenceRefs skinMod semanticNodes =
    (
        local refs = #()
        local pelvis = nodePos semanticNodes "Pelvis"
        local spine = nodePos semanticNodes "Spine"
        local chest = nodePos semanticNodes "Chest"
        local neck = nodePos semanticNodes "Neck"
        local head = nodePos semanticNodes "Head"

        addInfluenceRef refs skinMod semanticNodes "Pelvis" pelvis spine
        addInfluenceRef refs skinMod semanticNodes "Spine" pelvis chest
        addInfluenceRef refs skinMod semanticNodes "Chest" spine neck
        addInfluenceRef refs skinMod semanticNodes "Neck" chest head
        addInfluenceRef refs skinMod semanticNodes "Head" neck head

        for side in #("L", "R") do
        (
            local clav = nodePos semanticNodes (side + "_Clavicle")
            local upper = nodePos semanticNodes (side + "_UpperArm")
            local fore = nodePos semanticNodes (side + "_Forearm")
            local hand = nodePos semanticNodes (side + "_Hand")
            local handEnd = extrapolatedEnd hand fore 0.35 hand
            addInfluenceRef refs skinMod semanticNodes (side + "_Clavicle") chest upper
            addInfluenceRef refs skinMod semanticNodes (side + "_UpperArm") upper fore
            addInfluenceRef refs skinMod semanticNodes (side + "_Forearm") fore hand
            addInfluenceRef refs skinMod semanticNodes (side + "_Hand") hand handEnd

            local thigh = nodePos semanticNodes (side + "_Thigh")
            local calf = nodePos semanticNodes (side + "_Calf")
            local foot = nodePos semanticNodes (side + "_Foot")
            local toe = nodePos semanticNodes (side + "_Toe")
            addInfluenceRef refs skinMod semanticNodes (side + "_Thigh") thigh calf
            addInfluenceRef refs skinMod semanticNodes (side + "_Calf") calf foot
            addInfluenceRef refs skinMod semanticNodes (side + "_Foot") foot toe
            addInfluenceRef refs skinMod semanticNodes (side + "_Toe") foot toe
        )
        refs
    ),

    fn roleRadius role height =
    (
        local r = height * 0.10
        if role == "torso" do r = height * 0.18
        if role == "neck" do r = height * 0.10
        if role == "head" do r = height * 0.16
        if role == "clavicle" do r = height * 0.08
        if role == "arm" do r = height * 0.075
        if role == "hand" do r = height * 0.085
        if role == "leg" do r = height * 0.080
        if role == "foot" do r = height * 0.070
        if r < 0.1 do r = 0.1
        r
    ),

    fn sideAllowed p side centerX width =
    (
        local margin = width * 0.06
        if side == "C" then true
        else if side == "L" then p.x >= (centerX - margin)
        else if side == "R" then p.x <= (centerX + margin)
        else true
    ),

    fn pushBest best item limit =
    (
        local existing = 0
        for i = 1 to best.count do
        (
            if best[i][2] == item[2] do existing = i
        )
        if existing > 0 then
        (
            if item[1] < best[existing][1] do best[existing] = item
        )
        else append best item

        for i = 1 to best.count do
        (
            for j = (i + 1) to best.count do
            (
                if j <= best.count and best[j][1] < best[i][1] do
                (
                    local tmp = best[i]
                    best[i] = best[j]
                    best[j] = tmp
                )
            )
        )
        while best.count > limit do deleteItem best best.count
        best
    ),

    fn chooseWeights p refs fallbackBoneIndex bounds =
    (
        local mn = bounds[1]
        local mx = bounds[2]
        local size = mx - mn
        local height = abs size.z
        local width = abs size.x
        if height < 1.0 do height = 1.0
        if width < 1.0 do width = height * 0.4
        local centerX = (mn.x + mx.x) / 2.0
        local best = #()

        for ref in refs do
        (
            local side = ref[4]
            if sideAllowed p side centerX width do
            (
                local radius = roleRadius ref[3] height
                local d = distanceToSegment p ref[5] ref[6]
                local score = d / radius
                if ref[3] == "torso" and (p.x > centerX + width * 0.34 or p.x < centerX - width * 0.34) do score += 0.9
                if ref[3] == "head" and p.z < (mn.z + height * 0.55) do score += 1.2
                if ref[3] == "foot" and p.z > (mn.z + height * 0.32) do score += 1.0
                if ref[3] == "leg" and p.z > (mn.z + height * 0.55) do score += 1.0
                pushBest best #(score, ref[2], ref[1]) maxAssignedInfluences
            )
        )

        local usedFallback = false
        if best.count == 0 and fallbackBoneIndex > 0 do
        (
            append best #(0.0, fallbackBoneIndex, "Pelvis")
            usedFallback = true
        )

        local bones = #()
        local rawWeights = #()
        local total = 0.0
        for item in best do
        (
            local value = 1.0 / ((item[1] + 0.22) * (item[1] + 0.22))
            append bones item[2]
            append rawWeights value
            total += value
        )

        local weights = #()
        if total <= epsilon then
        (
            weights = #(1.0)
            if bones.count == 0 and fallbackBoneIndex > 0 do append bones fallbackBoneIndex
            usedFallback = true
        )
        else
        (
            for value in rawWeights do append weights (value / total)
        )
        #(bones, weights, usedFallback)
    ),

    fn replaceVertexWeightsSafe skinMod vertexIndex bones weights =
    (
        local ok = true
        try
        (
            skinOps.ReplaceVertexWeights skinMod vertexIndex bones weights
        )
        catch(ok = false)
        ok
    ),

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
    ),

    fn addSemanticWeight pairs semanticName weight =
    (
        if semanticName != undefined and weight > epsilon do
        (
            local found = 0
            for i = 1 to pairs.count do
            (
                if pairs[i][1] == semanticName do found = i
            )
            if found > 0 then
            (
                local item = pairs[found]
                pairs[found] = #(item[1], item[2] + weight)
            )
            else append pairs #(semanticName, weight)
        )
        pairs
    ),

    fn trimNormalizeSemanticPairs pairs limit =
    (
        local filtered = #()
        for item in pairs do
        (
            if item[2] > epsilon do append filtered #(item[1], item[2])
        )
        for i = 1 to filtered.count do
        (
            for j = (i + 1) to filtered.count do
            (
                if j <= filtered.count and filtered[j][2] > filtered[i][2] do
                (
                    local tmp = filtered[i]
                    filtered[i] = filtered[j]
                    filtered[j] = tmp
                )
            )
        )
        while filtered.count > limit do deleteItem filtered filtered.count

        local total = 0.0
        for item in filtered do total += item[2]
        if total > epsilon do
        (
            for i = 1 to filtered.count do
            (
                filtered[i] = #(filtered[i][1], filtered[i][2] / total)
            )
        )
        filtered
    ),

    fn normalizeBoneWeightAssignment bones weights fallbackBoneIndex =
    (
        local outBones = #()
        local outWeights = #()
        local total = 0.0
        for i = 1 to bones.count do
        (
            if i <= weights.count and weights[i] > epsilon do
            (
                local existing = findItem outBones bones[i]
                if existing > 0 then outWeights[existing] = outWeights[existing] + weights[i]
                else
                (
                    append outBones bones[i]
                    append outWeights weights[i]
                )
            )
        )
        for w in outWeights do total += w
        if total <= epsilon then
        (
            if fallbackBoneIndex > 0 then #( #(fallbackBoneIndex), #(1.0), true )
            else #( #(), #(), true )
        )
        else
        (
            for i = 1 to outWeights.count do outWeights[i] = outWeights[i] / total
            #(outBones, outWeights, false)
        )
    ),

    fn semanticSkinBoneIndexPairs skinMod semanticNodes =
    (
        local out = #()
        for item in semanticNodes do
        (
            local idx = skinBoneIndexForNode skinMod item[2]
            if idx > 0 do append out #(item[1], idx)
        )
        out
    ),

    fn skinBoneIndexForSemantic semanticIndexPairs semanticName =
    (
        for item in semanticIndexPairs do
        (
            if item[1] == semanticName do return item[2]
        )
        0
    ),

    fn assignmentFromReferencePairs semanticPairs semanticIndexPairs fallbackBoneIndex =
    (
        local bones = #()
        local weights = #()
        if semanticPairs != undefined do
        (
            for item in semanticPairs do
            (
                local idx = skinBoneIndexForSemantic semanticIndexPairs item[1]
                if idx > 0 do
                (
                    append bones idx
                    append weights item[2]
                )
            )
        )
        normalizeBoneWeightAssignment bones weights fallbackBoneIndex
    ),

    fn referenceMetaValue referenceMeta index defaultValue =
    (
        if referenceMeta == undefined then defaultValue
        else if referenceMeta.count < index then defaultValue
        else referenceMeta[index]
    ),

    fn findReferenceSkinObject =
    (
        local bestObj = undefined
        local bestSkin = undefined
        local bestVerts = 0
        for n in geometry do
        (
            local skinMod = findSkinModifier n
            if skinMod != undefined do
            (
                local verts = 0
                try(verts = skinOps.GetNumberVertices skinMod)catch(verts = 0)
                if verts == 0 do
                (
                    local tri = undefined
                    try(tri = snapshotAsMesh n)catch(tri = undefined)
                    if tri != undefined do
                    (
                        verts = tri.numverts
                        try(delete tri)catch()
                    )
                )
                if verts > bestVerts do
                (
                    bestVerts = verts
                    bestObj = n
                    bestSkin = skinMod
                )
            )
        )
        #(bestObj, bestSkin, bestVerts)
    ),

    fn extractReferenceCollapsedWeights referenceFbx =
    (
        local issues = #()
        local weightsByVertex = #()
        local found = findReferenceSkinObject()
        local refObj = found[1]
        local skinMod = found[2]
        local vertexCount = found[3]
        local totalInfluences = 0
        local mappedInfluences = 0
        local unmappedInfluences = 0
        local verticesWithMappedWeights = 0

        if refObj == undefined or skinMod == undefined then
        (
            append issues "No reference Skin object found after importing reference FBX."
        )
        else
        (
            for v = 1 to vertexCount do
            (
                local semanticPairs = #()
                local wc = 0
                try(wc = skinOps.GetVertexWeightCount skinMod v)catch(wc = 0)
                for i = 1 to wc do
                (
                    local boneId = 0
                    local weight = 0.0
                    local boneName = ""
                    try(boneId = skinOps.GetVertexWeightBoneID skinMod v i)catch(boneId = 0)
                    try(weight = skinOps.GetVertexWeight skinMod v i)catch(weight = 0.0)
                    if boneId > 0 do try(boneName = skinOps.GetBoneName skinMod boneId 0)catch(boneName = "")
                    totalInfluences += 1
                    local semanticName = referenceSemanticForBoneName boneName
                    if semanticName != undefined then
                    (
                        mappedInfluences += 1
                        addSemanticWeight semanticPairs semanticName weight
                    )
                    else
                    (
                        unmappedInfluences += 1
                    )
                )
                semanticPairs = trimNormalizeSemanticPairs semanticPairs maxAssignedInfluences
                if semanticPairs.count > 0 do verticesWithMappedWeights += 1
                append weightsByVertex semanticPairs
            )
        )

        local meta = #(referenceFbx, (if refObj != undefined then refObj.name else ""), vertexCount, totalInfluences, mappedInfluences, unmappedInfluences, verticesWithMappedWeights, issues.count)
        #(weightsByVertex, meta, issues)
    ),

    fn applyInitialWeightsToObject obj skinMod refs fallbackBoneIndex bounds =
    (
        local processed = 0
        local fallbackVertices = 0
        local failed = 0
        local maxInfluences = 0
        local verticesSeen = 0
        local tri = undefined

        try(tri = snapshotAsMesh obj)catch(tri = undefined)
        if tri != undefined do
        (
            local skinVerts = 0
            try(skinVerts = skinOps.GetNumberVertices skinMod)catch(skinVerts = tri.numverts)
            local count = if tri.numverts < skinVerts then tri.numverts else skinVerts
            for v = 1 to count do
            (
                verticesSeen += 1
                local p = (getVert tri v) * obj.objectTransform
                local assignment = chooseWeights p refs fallbackBoneIndex bounds
                local bones = assignment[1]
                local weights = assignment[2]
                if bones.count > 0 and weights.count > 0 then
                (
                    if replaceVertexWeightsSafe skinMod v bones weights then
                    (
                        processed += 1
                        if assignment[3] do fallbackVertices += 1
                        if bones.count > maxInfluences do maxInfluences = bones.count
                    )
                    else failed += 1
                )
                else
                (
                    failed += 1
                )
            )
            try(delete tri)catch()
        )
        try(skinOps.RemoveZeroWeights skinMod)catch()
        #(processed, fallbackVertices, failed, maxInfluences, verticesSeen)
    ),

    fn applyReferenceCollapsedWeightsToObject obj skinMod semanticIndexPairs referenceWeights refs fallbackBoneIndex bounds =
    (
        local processed = 0
        local fallbackVertices = 0
        local failed = 0
        local maxInfluences = 0
        local verticesSeen = 0
        local tri = undefined

        try(tri = snapshotAsMesh obj)catch(tri = undefined)
        if tri != undefined do
        (
            local skinVerts = 0
            try(skinVerts = skinOps.GetNumberVertices skinMod)catch(skinVerts = tri.numverts)
            local count = if tri.numverts < skinVerts then tri.numverts else skinVerts
            for v = 1 to count do
            (
                verticesSeen += 1
                local assignment = #( #(), #(), true )
                if v <= referenceWeights.count do
                (
                    assignment = assignmentFromReferencePairs referenceWeights[v] semanticIndexPairs fallbackBoneIndex
                )
                if assignment[3] do
                (
                    local p = (getVert tri v) * obj.objectTransform
                    assignment = chooseWeights p refs fallbackBoneIndex bounds
                    fallbackVertices += 1
                )

                local bones = assignment[1]
                local weights = assignment[2]
                if bones.count > 0 and weights.count > 0 then
                (
                    if replaceVertexWeightsSafe skinMod v bones weights then
                    (
                        processed += 1
                        if bones.count > maxInfluences do maxInfluences = bones.count
                    )
                    else failed += 1
                )
                else failed += 1
            )
            try(delete tri)catch()
        )
        try(skinOps.RemoveZeroWeights skinMod)catch()
        #(processed, fallbackVertices, failed, maxInfluences, verticesSeen)
    ),

    fn writeStage02Reports assetName objectResults issues bipedRoot semanticNodeCount stage01GateStatus stage01GateJson weightSource referenceMeta =
    (
        local dataDir = joinPath outDir "data"
        local reportsDir = joinPath outDir "reports"
        ensureDir outDir
        ensureDir dataDir
        ensureDir reportsDir

        local jsonPath = joinPath dataDir (assetName + "_stage02_skin_report.json")
        local mdPath = joinPath reportsDir (assetName + "_stage02_skin_report.md")

        local totalVertices = 0
        local totalProcessed = 0
        local totalFailed = 0
        local totalFallback = 0
        local maxInf = 0
        for item in objectResults do
        (
            totalVertices += item[8]
            totalProcessed += item[5]
            totalFallback += item[6]
            totalFailed += item[7]
            if item[9] > maxInf do maxInf = item[9]
        )

        local skinSetupReady = objectResults.count > 0 and totalProcessed > 0 and totalFailed == 0 and issues.count == 0
        local hasReferenceTransfer = referenceMeta != undefined and weightSource == "reference_collapsed_skin_weights"
        local weightNote = if hasReferenceTransfer then "Weights are collapsed from the imported reference Skin onto the simplified Biped semantic bones." else "Weights are generated from Biped segment proximity and side/height gates."

        local fp = createFile jsonPath
        format "{\n" to:fp
        format "  \"assetName\": %, \n" (jsonString assetName) to:fp
        format "  \"scene\": %, \n" (jsonString (maxFilePath + maxFileName)) to:fp
        format "  \"generatedAt\": %, \n" (jsonString (localTime as string)) to:fp
        format "  \"stage\": %, \n" (jsonString "stage02_initial_skin_setup") to:fp
        format "  \"tutorialSources\": [%, %],\n" (jsonString "BV1ftReBYEg3-03-skin-setup-and-prop-weights") (jsonString "BV1ftReBYEg3-04-body-weights-and-final-check") to:fp
        format "  \"decisionPolicy\": %, \n" (jsonString "first_pass_skin_only_not_production_delivery") to:fp
        format "  \"weightSource\": %, \n" (jsonString weightSource) to:fp
        if hasReferenceTransfer then
        (
            format "  \"referenceTransfer\": {\"referenceFbx\": %, \"referenceSkinObject\": %, \"referenceVertices\": %, \"referenceInfluences\": %, \"mappedInfluences\": %, \"unmappedInfluences\": %, \"verticesWithMappedWeights\": %, \"extractionIssueCount\": %},\n" \
                (jsonString (referenceMetaValue referenceMeta 1 "")) (jsonString (referenceMetaValue referenceMeta 2 "")) (referenceMetaValue referenceMeta 3 0) (referenceMetaValue referenceMeta 4 0) (referenceMetaValue referenceMeta 5 0) (referenceMetaValue referenceMeta 6 0) (referenceMetaValue referenceMeta 7 0) (referenceMetaValue referenceMeta 8 0) to:fp
        )
        else
        (
            format "  \"referenceTransfer\": null,\n" to:fp
        )
        format "  \"stage01GateStatus\": %, \n" (jsonString stage01GateStatus) to:fp
        format "  \"stage01GateJson\": %, \n" (jsonString stage01GateJson) to:fp
        format "  \"bipedRoot\": %, \n" (jsonString (if bipedRoot != undefined then bipedRoot.name else "")) to:fp
        format "  \"bipedDeformingNodeCount\": %, \n" semanticNodeCount to:fp
        format "  \"boneAffectLimitRequested\": %, \n" boneAffectLimit to:fp
        format "  \"maxAssignedInfluences\": %, \n" maxAssignedInfluences to:fp
        format "  \"skinSetupReady\": %, \n" (jsonBool skinSetupReady) to:fp
        format "  \"skinWeightsComplete\": false,\n" to:fp
        format "  \"deformationTestComplete\": false,\n" to:fp
        format "  \"productionReady\": false,\n" to:fp
        format "  \"totals\": {\"verticesSeen\": %, \"verticesProcessed\": %, \"fallbackVertices\": %, \"failedVertices\": %, \"maxAssignedInfluences\": %},\n" totalVertices totalProcessed totalFallback totalFailed maxInf to:fp
        format "  \"skinPolicy\": {\n" to:fp
        format "    \"bipedCom\": %, \n" (jsonString "control_only_non_deforming_not_added_to_skin") to:fp
        format "    \"templateBones\": %, \n" (jsonString "AIRA_BONE_* nodes are ignored by Stage02 skin setup") to:fp
        format "    \"accessoryBones\": %\n" (jsonString "prop/accessory-specific bones remain manual or future Stage02 extension work") to:fp
        format "  },\n" to:fp
        format "  \"skinObjects\": [\n" to:fp
        for i = 1 to objectResults.count do
        (
            local item = objectResults[i]
            format "    {\"name\": %, \"existingSkin\": %, \"skinBoneReferenceCount\": %, \"bonesAddedAttempted\": %, \"verticesProcessed\": %, \"fallbackVertices\": %, \"failedVertices\": %, \"verticesSeen\": %, \"maxAssignedInfluences\": %}" \
                (jsonString item[1]) (jsonBool item[2]) item[3] item[4] item[5] item[6] item[7] item[8] item[9] to:fp
            if i < objectResults.count then format ",\n" to:fp else format "\n" to:fp
        )
        format "  ],\n" to:fp
        format "  \"tutorialTasks\": [\n" to:fp
        format "    {\"id\": \"add_skin_modifier\", \"status\": %, \"note\": %},\n" (jsonString (if objectResults.count > 0 then "done" else "blocked")) (jsonString "Skin modifier is added to model geometry when missing.") to:fp
        format "    {\"id\": \"add_biped_bones_to_skin\", \"status\": %, \"note\": %},\n" (jsonString (if semanticNodeCount > 0 then "done" else "blocked")) (jsonString "Only deforming Biped nodes are added; COM stays control-only.") to:fp
        format "    {\"id\": \"set_bone_affect_limit\", \"status\": %, \"note\": %},\n" (jsonString "attempted") (jsonString "Tutorial demo uses 3; project QC still requires <= 4.") to:fp
        format "    {\"id\": \"initial_weight_pass\", \"status\": %, \"note\": %},\n" (jsonString (if totalProcessed > 0 then "done_first_pass" else "blocked")) (jsonString weightNote) to:fp
        if hasReferenceTransfer do
        (
            format "    {\"id\": \"reference_weight_collapse\", \"status\": %, \"note\": %},\n" (jsonString (if (referenceMetaValue referenceMeta 7 0) > 0 then "done_first_pass" else "blocked")) (jsonString weightNote) to:fp
        )
        format "    {\"id\": \"remove_zero_weights\", \"status\": %, \"note\": %},\n" (jsonString "attempted") (jsonString "skinOps.RemoveZeroWeights is called when available.") to:fp
        format "    {\"id\": \"deformation_test\", \"status\": %, \"note\": %}\n" (jsonString "required_manual_followup") (jsonString "Tutorial-style head, torso, arm, leg, foot and prop motion tests are still required.") to:fp
        format "  ],\n" to:fp
        format "  \"issues\": %\n" (jsonStringArray issues) to:fp
        format "}\n" to:fp
        close fp

        fp = createFile mdPath
        format "# Stage02 Skin Setup: %\n\n" assetName to:fp
        format "- Scene: `%`\n" (maxFilePath + maxFileName) to:fp
        format "- Generated: `%`\n" localTime to:fp
        format "- Stage01 gate status: `%`\n" stage01GateStatus to:fp
        format "- Weight source: `%`\n" weightSource to:fp
        if hasReferenceTransfer do
        (
            format "- Reference FBX: `%`\n" (referenceMetaValue referenceMeta 1 "") to:fp
            format "- Reference Skin object: `%`\n" (referenceMetaValue referenceMeta 2 "") to:fp
            format "- Reference vertices with mapped weights: `% / %`\n" (referenceMetaValue referenceMeta 7 0) (referenceMetaValue referenceMeta 3 0) to:fp
            format "- Reference mapped influences: `% / %`\n" (referenceMetaValue referenceMeta 5 0) (referenceMetaValue referenceMeta 4 0) to:fp
        )
        format "- Biped root: `%`\n" (if bipedRoot != undefined then bipedRoot.name else "") to:fp
        format "- Biped deforming nodes: `%`\n" semanticNodeCount to:fp
        format "- Bone affect limit requested: `%`\n" boneAffectLimit to:fp
        format "- Vertices processed: `% / %`\n" totalProcessed totalVertices to:fp
        format "- Fallback vertices: `%`\n" totalFallback to:fp
        format "- Failed vertices: `%`\n" totalFailed to:fp
        format "- Skin setup ready: `%`\n" skinSetupReady to:fp
        format "- Skin weights complete: `false`\n" to:fp
        format "- Deformation test complete: `false`\n" to:fp
        format "- Production ready: `false`\n" to:fp
        format "\n## Skin Objects\n\n" to:fp
        if objectResults.count == 0 then
        (
            format "- None\n" to:fp
        )
        else
        (
            for item in objectResults do
            (
                format "- `%`: existingSkin=`%`, skinBones=`%`, processed=`%`, failed=`%`, maxAssignedInfluences=`%`\n" item[1] item[2] item[3] item[5] item[7] item[9] to:fp
            )
        )
        format "\n## Tutorial Task Status\n\n" to:fp
        format "- Skin modifier: `%`\n" (objectResults.count > 0) to:fp
        format "- Add Biped bones to Skin: `%`\n" (semanticNodeCount > 0) to:fp
        format "- Bone Affect Limit: `%`\n" boneAffectLimit to:fp
        format "- Initial weights: `%`\n" (totalProcessed > 0) to:fp
        if hasReferenceTransfer do format "- Reference weight collapse: `%`\n" ((referenceMetaValue referenceMeta 7 0) > 0) to:fp
        format "- Remove 0 weights: `attempted`\n" to:fp
        format "- Manual deformation tests: `required`\n" to:fp
        format "\n## Policy Notes\n\n" to:fp
        format "- Biped COM / vertical root is treated as control-only and is not added as a deforming Skin bone.\n" to:fp
        format "- `AIRA_BONE_*` template bones are ignored; Stage02 follows the current Biped-only body flow.\n" to:fp
        if hasReferenceTransfer do format "- Reference AccuRig-style Skin weights are used only as source data, then collapsed to the simplified Biped deforming set.\n" to:fp
        format "- Accessory/prop-specific weighting is not considered production-complete by this first pass.\n" to:fp
        format "\n## Issues\n\n" to:fp
        if issues.count == 0 then
        (
            format "- None for mechanical setup. Manual weight and deformation review still required.\n" to:fp
        )
        else
        (
            for issue in issues do format "- %\n" issue to:fp
        )
        format "\n## Output\n\n" to:fp
        format "- JSON: `%`\n" jsonPath to:fp
        close fp

        #(jsonPath, mdPath, skinSetupReady, issues.count)
    ),

    fn runInitialSkin assetName =
    (
        if assetName == undefined or assetName == "" do assetName = "current_scene"
        ensureDir outDir
        ensureDir (joinPath outDir "data")
        ensureDir (joinPath outDir "reports")

        local issues = #()
        local modelNodes = geometryNodes()
        local bounds = getBounds modelNodes
        local bipRoot = findBipedRoot()
        local stage01GateStatus = getEnv "AIRA_STAGE02_STAGE01_GATE_STATUS" "not_provided"
        local stage01GateJson = getEnv "AIRA_STAGE02_STAGE01_GATE_JSON" ""

        if stage01GateStatus != "skin_setup_ready" do append issues ("Stage01 Skin Prep Gate is not ready (" + stage01GateStatus + "); Stage02 output is research-only and must not be treated as production.")
        if modelNodes.count == 0 do append issues "No candidate geometry nodes found for Skin."
        if bounds == undefined do append issues "Could not compute model bounds."
        if bipRoot == undefined do append issues "No Stage01-style Biped root found."

        local semanticNodes = semanticBipedNodes bipRoot
        if semanticNodes.count == 0 do append issues "No deforming Biped nodes could be resolved."

        local objectResults = #()
        if modelNodes.count > 0 and bounds != undefined and bipRoot != undefined and semanticNodes.count > 0 do
        (
            for obj in modelNodes do
            (
                local skinResult = ensureSkinModifier obj
                local skinMod = skinResult[1]
                local existed = skinResult[2]
                if skinMod == undefined then
                (
                    append issues ("Could not add/find Skin modifier on " + obj.name + ".")
                )
                else
                (
                    setSkinBoneAffectLimit skinMod
                    local addResult = addBipedBonesToSkin skinMod semanticNodes
                    local refs = buildInfluenceRefs skinMod semanticNodes
                    local pelvisNode = semanticNode semanticNodes "Pelvis"
                    local fallbackBoneIndex = if pelvisNode != undefined then skinBoneIndexForNode skinMod pelvisNode else 0
                    if refs.count == 0 do append issues ("No Skin influence refs were built for " + obj.name + ".")
                    if fallbackBoneIndex == 0 do append issues ("Pelvis fallback Skin bone missing for " + obj.name + ".")

                    local applyResult = #(0, 0, 0, 0, 0)
                    if refs.count > 0 and fallbackBoneIndex > 0 do
                    (
                        applyResult = applyInitialWeightsToObject obj skinMod refs fallbackBoneIndex bounds
                    )
                    local skinBoneCount = 0
                    try(skinBoneCount = skinOps.GetNumberBones skinMod)catch(skinBoneCount = 0)
                    append objectResults #(obj.name, existed, skinBoneCount, addResult[1], applyResult[1], applyResult[2], applyResult[3], applyResult[5], applyResult[4])
                )
            )
        )

        local reports = writeStage02Reports assetName objectResults issues bipRoot semanticNodes.count stage01GateStatus stage01GateJson "heuristic_biped_segment_proximity" undefined
        log ("Stage02 report written: " + reports[1])
        reports
    ),

    fn runReferenceCollapsedSkin assetName referenceWeights referenceMeta =
    (
        if assetName == undefined or assetName == "" do assetName = "current_scene"
        ensureDir outDir
        ensureDir (joinPath outDir "data")
        ensureDir (joinPath outDir "reports")

        local issues = #()
        local modelNodes = geometryNodes()
        local bounds = getBounds modelNodes
        local bipRoot = findBipedRoot()
        local stage01GateStatus = getEnv "AIRA_STAGE02_STAGE01_GATE_STATUS" "not_provided"
        local stage01GateJson = getEnv "AIRA_STAGE02_STAGE01_GATE_JSON" ""
        local hasReferenceWeights = false
        if referenceWeights != undefined do hasReferenceWeights = referenceWeights.count > 0

        if stage01GateStatus != "skin_setup_ready" do append issues ("Stage01 Skin Prep Gate is not ready (" + stage01GateStatus + "); Stage02 output is research-only and must not be treated as production.")
        if not hasReferenceWeights do append issues "Reference collapsed weights are empty; cannot run reference-guided Stage02 weights."
        if (referenceMetaValue referenceMeta 8 0) > 0 do append issues "Reference Skin extraction reported issues; inspect batch summary and listener log."
        if modelNodes.count == 0 do append issues "No candidate geometry nodes found for Skin."
        if bounds == undefined do append issues "Could not compute model bounds."
        if bipRoot == undefined do append issues "No Stage01-style Biped root found."

        local semanticNodes = semanticBipedNodes bipRoot
        if semanticNodes.count == 0 do append issues "No deforming Biped nodes could be resolved."

        local objectResults = #()
        if modelNodes.count > 0 and bounds != undefined and bipRoot != undefined and semanticNodes.count > 0 do
        (
            for obj in modelNodes do
            (
                local skinResult = ensureSkinModifier obj
                local skinMod = skinResult[1]
                local existed = skinResult[2]
                if skinMod == undefined then
                (
                    append issues ("Could not add/find Skin modifier on " + obj.name + ".")
                )
                else
                (
                    setSkinBoneAffectLimit skinMod
                    local addResult = addBipedBonesToSkin skinMod semanticNodes
                    local refs = buildInfluenceRefs skinMod semanticNodes
                    local semanticIndexPairs = semanticSkinBoneIndexPairs skinMod semanticNodes
                    local pelvisNode = semanticNode semanticNodes "Pelvis"
                    local fallbackBoneIndex = if pelvisNode != undefined then skinBoneIndexForNode skinMod pelvisNode else 0
                    if refs.count == 0 do append issues ("No Skin influence refs were built for " + obj.name + ".")
                    if semanticIndexPairs.count == 0 do append issues ("No semantic Skin bone index map was built for " + obj.name + ".")
                    if fallbackBoneIndex == 0 do append issues ("Pelvis fallback Skin bone missing for " + obj.name + ".")

                    local applyResult = #(0, 0, 0, 0, 0)
                    if refs.count > 0 and semanticIndexPairs.count > 0 and fallbackBoneIndex > 0 and hasReferenceWeights do
                    (
                        applyResult = applyReferenceCollapsedWeightsToObject obj skinMod semanticIndexPairs referenceWeights refs fallbackBoneIndex bounds
                    )
                    local skinBoneCount = 0
                    try(skinBoneCount = skinOps.GetNumberBones skinMod)catch(skinBoneCount = 0)
                    append objectResults #(obj.name, existed, skinBoneCount, addResult[1], applyResult[1], applyResult[2], applyResult[3], applyResult[5], applyResult[4])
                )
            )
        )

        local reports = writeStage02Reports assetName objectResults issues bipRoot semanticNodes.count stage01GateStatus stage01GateJson "reference_collapsed_skin_weights" referenceMeta
        log ("Stage02 reference-collapsed report written: " + reports[1])
        reports
    )
)

AIRA_Stage02 = AIRAStage02SkinTool()

if AIRA_STAGE02_HEADLESS != true do
(
    try(destroyDialog AIRA_Stage02_UI)catch()

    rollout AIRA_Stage02_UI "AIRA Stage02 Skin" width:310 height:185
    (
        label lblTitle "Independent Skin setup for an existing Biped scene" pos:[10,10] width:290 height:18
        editText edtAsset "Asset" text:"current_scene" pos:[10,35] width:290 height:18
        spinner spnLimit "Bone Affect Limit" range:[1,4,3] type:#integer pos:[10,65] width:190 height:18
        button btnRun "Run Initial Skin Setup" pos:[25,100] width:260 height:25
        button btnOpenOut "Print Output Dir" pos:[25,132] width:260 height:25

        on btnRun pressed do
        (
            AIRA_Stage02.boneAffectLimit = spnLimit.value
            AIRA_Stage02.maxAssignedInfluences = spnLimit.value
            local result = AIRA_Stage02.runInitialSkin edtAsset.text
            messageBox ("Stage02 Skin report:\n" + result[1]) title:"AIRA Stage02"
        )

        on btnOpenOut pressed do
        (
            format "[AIRA Stage02] Output dir: %\n" AIRA_Stage02.outDir
        )
    )

    createDialog AIRA_Stage02_UI
    AIRA_Stage02.log "Loaded. Use the AIRA Stage02 Skin window."
)

if AIRA_STAGE02_HEADLESS == true do
(
    AIRA_Stage02.log "Loaded in headless mode."
)
