/*
AI Rig Assistant - Stage 01 Biped Guide Tool
Target: 3ds Max 2020+ / MAXScript

This script implements the first tutorial stage:
- create draggable rig guide points from the selected character bounds
- mirror left-side guides to the right side
- create a Biped with a project-friendly structure
- fit major Biped nodes to the guides in Figure Mode
- validate guide symmetry and generate a Markdown report

Usage:
1. In 3ds Max, run this file from Scripting > Run Script.
2. Select the character model.
3. Click "Create / Update Guides".
4. Move the guides onto the model joints.
5. Click "Mirror L Guides To R" if you only adjusted the left side.
6. Click "Create Biped From Guides".
7. Click "Validate / Report".
*/

global AIRA_Stage01
global AIRA_Stage01_UI
global AIRA_STAGE01_HEADLESS

struct AIRAStage01Tool
(
    prefix = "AIRA",
    guidePrefix = "AIRA_GUIDE_",
    layerName = "AIRA_Guides",
    bipedName = "AIRA_Biped_COM",
    guideSize = 5.0,
    defaultHeight = 160.0,
    facingAngle = -90.0,
    symmetryTolerance = 2.0,
    minFitTolerance = 2.0,
    fitToleranceRatio = 0.050,
    ctWrapToleranceRatio = 0.006,
    ctWrapMaxStepRatio = 0.045,
    ctWrapDamping = 0.65,
    ctWrapSectorCount = 16,
    ctWrapMinSectorCoverage = 0.62,
    guideAlgorithm = "tutorial_centerline_qbird",
    cachedEnvelopePoints = undefined,
    cachedEnvelopeNodeCount = 0,

    fn log msg =
    (
        format "[AIRA Stage01] %\n" msg
    ),

    fn minPoint a b =
    (
        [(if a.x < b.x then a.x else b.x), (if a.y < b.y then a.y else b.y), (if a.z < b.z then a.z else b.z)]
    ),

    fn maxPoint a b =
    (
        [(if a.x > b.x then a.x else b.x), (if a.y > b.y then a.y else b.y), (if a.z > b.z then a.z else b.z)]
    ),

    fn isGuideNode n =
    (
        (isValidNode n) and (matchPattern n.name pattern:(guidePrefix + "*"))
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

    fn isCandidateModelNode n =
    (
        if not (isValidNode n) then false
        else if isGuideNode n then false
        else if isBipedLikeNode n then false
        else if matchPattern n.name pattern:(prefix + "_BONE_*") ignoreCase:true then false
        else
        (
            local ok = true
            try
            (
                local mn = n.min
                local mx = n.max
            )
            catch
            (
                ok = false
            )
            ok
        )
    ),

    fn selectedModelNodes =
    (
        for n in selection where isCandidateModelNode n collect n
    ),

    fn sceneModelNodes =
    (
        for n in geometry where isCandidateModelNode n collect n
    ),

    fn reportModelNodes =
    (
        local nodes = selectedModelNodes()
        if nodes.count == 0 then sceneModelNodes() else nodes
    ),

    fn getBounds nodes =
    (
        if nodes == undefined or nodes.count == 0 then undefined
        else
        (
            local mn = [1e9, 1e9, 1e9]
            local mx = [-1e9, -1e9, -1e9]

            for n in nodes where isCandidateModelNode n do
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

    fn collectWorldMeshPoints nodes =
    (
        local pts = #()
        if nodes != undefined do
        (
            for n in nodes where isCandidateModelNode n do
            (
                try
                (
                    local tri = snapshotAsMesh n
                    for v = 1 to tri.numverts do
                    (
                        local p = (getVert tri v) * n.objectTransform
                        append pts p
                    )
                    delete tri
                )
                catch()
            )
        )
        pts
    ),

    fn percentileValue values ratio fallback =
    (
        if values == undefined or values.count == 0 then fallback
        else
        (
            local sorted = for item in values collect item
            sort sorted
            local idx = 1 + ((floor ((sorted.count - 1) * ratio)) as integer)
            if idx < 1 do idx = 1
            if idx > sorted.count do idx = sorted.count
            sorted[idx]
        )
    ),

    fn weightedSlicePercentile counts valuesBySlice sliceCount lowRatio highRatio ratio fallback =
    (
        local weightedSum = 0.0
        local total = 0
        for i = 1 to sliceCount do
        (
            local sliceRatio = ((i as float) - 0.5) / sliceCount
            if sliceRatio >= lowRatio and sliceRatio <= highRatio and counts[i] > 0 do
            (
                local v = percentileValue valuesBySlice[i] ratio fallback
                weightedSum += v * counts[i]
                total += counts[i]
            )
        )
        if total > 0 then (weightedSum / total) else fallback
    ),

    fn analyzeBodyProfile nodes bounds =
    (
        if nodes == undefined do nodes = sceneModelNodes()
        if bounds == undefined do bounds = getBounds nodes
        if bounds == undefined do bounds = #([ -35, -25, 0 ], [35, 25, defaultHeight])

        local mn = bounds[1]
        local mx = bounds[2]
        local size = mx - mn
        local center = (mn + mx) / 2.0
        local h = if abs(size.z) > 1.0 then abs(size.z) else defaultHeight
        local width = if abs(size.x) > 1.0 then abs(size.x) else h * 0.60
        local depth = if abs(size.y) > 1.0 then abs(size.y) else h * 0.40
        local widthHeightRatio = width / h
        local depthHeightRatio = depth / h
        local z0 = mn.z
        local sliceCount = 28
        local counts = #()
        local xMins = #()
        local xMaxs = #()
        local yMins = #()
        local yMaxs = #()
        local xSums = #()
        local ySums = #()
        local xVals = #()
        local yVals = #()

        for i = 1 to sliceCount do
        (
            append counts 0
            append xMins 1e9
            append xMaxs -1e9
            append yMins 1e9
            append yMaxs -1e9
            append xSums 0.0
            append ySums 0.0
            append xVals #()
            append yVals #()
        )

        local pts = collectWorldMeshPoints nodes
        for p in pts do
        (
            local ratio = (p.z - z0) / h
            local idx = ((floor (ratio * sliceCount)) as integer) + 1
            if idx < 1 do idx = 1
            if idx > sliceCount do idx = sliceCount

            counts[idx] += 1
            if p.x < xMins[idx] do xMins[idx] = p.x
            if p.x > xMaxs[idx] do xMaxs[idx] = p.x
            if p.y < yMins[idx] do yMins[idx] = p.y
            if p.y > yMaxs[idx] do yMaxs[idx] = p.y
            xSums[idx] += p.x
            ySums[idx] += p.y
            append xVals[idx] p.x
            append yVals[idx] p.y
        )

        local maxWidth = width
        local maxWidthRatio = 0.50
        local maxArmWidth = width
        local armRatio = 0.58
        local lowerMaxWidth = width * 0.30
        local footHalf = width * 0.12
        local footY = center.y - depth * 0.18
        local toeY = center.y - depth * 0.42
        local semanticMaxWidth = width
        local semanticMaxWidthRatio = 0.50
        local semanticArmWidth = width
        local semanticArmRatio = 0.58
        local semanticCoreHalf = width * 0.18
        local semanticShoulderHalf = width * 0.24
        local semanticElbowHalf = width * 0.34
        local semanticWristHalf = width * 0.44
        local semanticFootHalf = width * 0.11
        local semanticFootY = footY
        local semanticToeY = toeY
        local semanticLowerRobeWidth = 0.0
        local semanticLowerRobeDepth = 0.0
        local semanticLowerRobeY = center.y
        local semanticLegOcclusionRisk = false

        for i = 1 to sliceCount do
        (
            if counts[i] > 0 do
            (
                local sliceRatio = ((i as float) - 0.5) / sliceCount
                local sliceWidth = xMaxs[i] - xMins[i]
                local sliceDepth = yMaxs[i] - yMins[i]
                local x05 = percentileValue xVals[i] 0.05 xMins[i]
                local x25 = percentileValue xVals[i] 0.25 xMins[i]
                local x75 = percentileValue xVals[i] 0.75 xMaxs[i]
                local x95 = percentileValue xVals[i] 0.95 xMaxs[i]
                local y05 = percentileValue yVals[i] 0.05 yMins[i]
                local y50 = percentileValue yVals[i] 0.50 center.y
                local y95 = percentileValue yVals[i] 0.95 yMaxs[i]
                local robustWidth = x95 - x05
                local robustDepth = y95 - y05
                local coreWidth = x75 - x25
                if sliceWidth > maxWidth do
                (
                    maxWidth = sliceWidth
                    maxWidthRatio = sliceRatio
                )
                if robustWidth > semanticMaxWidth do
                (
                    semanticMaxWidth = robustWidth
                    semanticMaxWidthRatio = sliceRatio
                )
                if sliceRatio >= 0.34 and sliceRatio <= 0.72 and sliceWidth > maxArmWidth do
                (
                    maxArmWidth = sliceWidth
                    armRatio = sliceRatio
                )
                if sliceRatio >= 0.34 and sliceRatio <= 0.72 and robustWidth > semanticArmWidth do
                (
                    semanticArmWidth = robustWidth
                    semanticArmRatio = sliceRatio
                    semanticCoreHalf = coreWidth * 0.50
                    semanticShoulderHalf = if (coreWidth * 0.52) > (robustWidth * 0.24) then (coreWidth * 0.52) else (robustWidth * 0.24)
                    semanticElbowHalf = robustWidth * 0.37
                    semanticWristHalf = robustWidth * 0.47
                )
                if sliceRatio >= 0.02 and sliceRatio <= 0.16 and sliceWidth > lowerMaxWidth do
                (
                    lowerMaxWidth = sliceWidth
                    footHalf = sliceWidth * 0.28
                    footY = (yMins[i] + yMaxs[i]) / 2.0
                    toeY = yMins[i]
                )
                if sliceRatio >= 0.02 and sliceRatio <= 0.16 and robustWidth > (semanticFootHalf * 2.0) do
                (
                    semanticFootHalf = robustWidth * 0.22
                    semanticFootY = y50
                    semanticToeY = y05
                )
                if sliceRatio >= 0.16 and sliceRatio <= 0.34 and robustWidth > semanticLowerRobeWidth do
                (
                    semanticLowerRobeWidth = robustWidth
                    semanticLowerRobeDepth = robustDepth
                    semanticLowerRobeY = y50
                )
            )
        )

        local semanticWaistY = weightedSlicePercentile counts yVals sliceCount 0.30 0.44 0.50 center.y
        local semanticTorsoY = weightedSlicePercentile counts yVals sliceCount 0.42 0.66 0.50 center.y
        local semanticUpperY = weightedSlicePercentile counts yVals sliceCount 0.62 0.78 0.50 semanticTorsoY
        local semanticHeadY = weightedSlicePercentile counts yVals sliceCount 0.78 0.90 0.50 semanticUpperY
        local semanticHeadTopY = weightedSlicePercentile counts yVals sliceCount 0.86 0.92 0.50 semanticHeadY
        local semanticCrestX = weightedSlicePercentile counts xVals sliceCount 0.92 1.00 0.50 center.x
        local semanticCrestY = weightedSlicePercentile counts yVals sliceCount 0.92 1.00 0.50 semanticHeadTopY

        local armHalf = maxArmWidth * 0.50
        local shoulderHalf = armHalf * 0.58
        local elbowHalf = armHalf * 0.78
        local wristHalf = armHalf * 0.95
        local pelvisZ = z0 + h * 0.36
        local hipZ = z0 + h * 0.32
        local kneeZ = z0 + h * 0.18
        local ankleZ = z0 + h * 0.07
        local footZ = z0 + h * 0.035
        local toeZ = z0 + h * 0.035
        local armZ = z0 + h * armRatio
        local chestZ = z0 + h * 0.58
        local neckZ = z0 + h * 0.74
        local headZ = z0 + h * 0.84
        local headTopZ = z0 + h * 0.98
        local crestTopZ = z0 + h * 0.98
        local bodyType = "unknown"
        local notes = #()

        if widthHeightRatio >= 0.75 and maxWidthRatio >= 0.30 and maxWidthRatio <= 0.72 then
        (
            bodyType = "compact_q_bird_wide_body_short_legs"
            append notes "Wide compact Q-style silhouette with strong horizontal arm/wing span."
        )
        else if widthHeightRatio >= 0.60 then
        (
            bodyType = "wide_stylized_character"
            append notes "Wide stylized silhouette."
        )
        else
        (
            bodyType = "slender_or_standard_character"
            append notes "Less compact silhouette."
        )

        if depthHeightRatio >= 0.45 do append notes "Deep body volume; side-view thickness should be considered when placing pelvis/chest guides."
        if armRatio < 0.48 or armRatio > 0.68 do append notes ("Detected arm-span height is unusual: " + (armRatio as string))
        if semanticMaxWidth < maxWidth * 0.80 do append notes "Robust percentile width differs from raw max width; accessories or separated parts may affect raw silhouette."
        semanticLegOcclusionRisk = (bodyType == "compact_q_bird_wide_body_short_legs") and (semanticLowerRobeWidth > (semanticFootHalf * 3.0))
        if semanticLegOcclusionRisk do append notes "Lower-body garment/robe silhouette is much wider than the visible foot span; leg landmarks must be placed by under-clothing anatomy, not the garment edge."
        append notes "Initial landmark estimates are mesh-profile based, not final anatomical proof."

        #(
            mn, mx, size, center,
            h, width, depth, widthHeightRatio, depthHeightRatio,
            armZ, pelvisZ, hipZ, kneeZ, ankleZ, footZ, toeZ,
            shoulderHalf, elbowHalf, wristHalf, footHalf, footY, toeY,
            chestZ, neckZ, headZ, headTopZ,
            bodyType, notes, maxWidth, maxWidthRatio, pts.count,
            semanticShoulderHalf, semanticElbowHalf, semanticWristHalf, semanticFootHalf,
            semanticFootY, semanticToeY, semanticArmRatio, semanticMaxWidth, semanticMaxWidthRatio,
            semanticCoreHalf,
            semanticWaistY, semanticTorsoY, semanticUpperY, semanticHeadY, semanticHeadTopY,
            semanticCrestX, semanticCrestY,
            semanticLowerRobeWidth, semanticLowerRobeDepth, semanticLowerRobeY, semanticLegOcclusionRisk
        )
    ),

    fn getGuide name =
    (
        getNodeByName (guidePrefix + name)
    ),

    fn setNodeWireColor n c =
    (
        try(n.wirecolor = c)catch()
    ),

    fn ensureGuideLayer node =
    (
        try
        (
            local layer = LayerManager.getLayerFromName layerName
            if layer == undefined do layer = LayerManager.newLayerFromName layerName
            layer.addNode node
        )
        catch()
    ),

    fn createOrUpdateGuide name pos colorValue =
    (
        local fullName = guidePrefix + name
        local g = getNodeByName fullName

        if g == undefined then
        (
            g = point name:fullName pos:pos size:guideSize box:false cross:true axistripod:false centermarker:true
            try(setUserProp g "AIRA_Type" "Stage01Guide")catch()
            ensureGuideLayer g
        )
        else
        (
            g.pos = pos
            try(g.size = guideSize)catch()
        )

        setNodeWireColor g colorValue
        g
    ),

    fn medianPoint points fallback =
    (
        if points == undefined or points.count == 0 then fallback
        else
        (
            local xs = #()
            local ys = #()
            local zs = #()
            for p in points do
            (
                append xs p.x
                append ys p.y
                append zs p.z
            )
            local mx = percentileValue xs 0.50 fallback.x
            local my = percentileValue ys 0.50 fallback.y
            local mz = percentileValue zs 0.50 fallback.z
            [mx, my, mz]
        )
    ),

    fn centerlinePoint points fallback =
    (
        if points == undefined or points.count == 0 then fallback
        else
        (
            local xs = #()
            local ys = #()
            local zs = #()
            for p in points do
            (
                append xs p.x
                append ys p.y
                append zs p.z
            )
            local x0 = percentileValue xs 0.12 fallback.x
            local x1 = percentileValue xs 0.88 fallback.x
            local y0 = percentileValue ys 0.12 fallback.y
            local y1 = percentileValue ys 0.88 fallback.y
            local z0p = percentileValue zs 0.12 fallback.z
            local z1p = percentileValue zs 0.88 fallback.z
            [((x0 + x1) / 2.0), ((y0 + y1) / 2.0), ((z0p + z1p) / 2.0)]
        )
    ),

    fn visualOuterHandTarget side center h w d z0 fallback =
    (
        local pts = collectWorldMeshPoints (sceneModelNodes())
        local candidates = #()
        local sideValues = #()
        for p in pts do
        (
            local sx = (p.x - center.x) * side
            if sx > (w * 0.25) and \
               p.y >= (center.y - d * 0.38) and p.y <= (center.y + d * 0.32) and \
               p.z >= (z0 + h * 0.25) and p.z <= (z0 + h * 0.58) do
            (
                append candidates p
                append sideValues sx
            )
        )

        if candidates.count < 8 then fallback
        else
        (
            local cutoff = percentileValue sideValues 0.88 (w * 0.38)
            local outer = #()
            for p in candidates do
            (
                local sx = (p.x - center.x) * side
                if sx >= cutoff do append outer p
            )

            medianPoint outer fallback
        )
    ),

    fn visualHandCenterTarget side center h w d z0 fallback =
    (
        local pts = collectWorldMeshPoints (sceneModelNodes())
        local candidates = #()
        local sideValues = #()
        for p in pts do
        (
            local sx = (p.x - center.x) * side
            if sx > (w * 0.25) and \
               p.y >= (center.y - d * 0.38) and p.y <= (center.y + d * 0.32) and \
               p.z >= (z0 + h * 0.25) and p.z <= (z0 + h * 0.58) do
            (
                append candidates p
                append sideValues sx
            )
        )

        if candidates.count < 8 then fallback
        else
        (
            local cutoff = percentileValue sideValues 0.70 (w * 0.34)
            local handMass = #()
            for p in candidates do
            (
                local sx = (p.x - center.x) * side
                if sx >= cutoff do append handMass p
            )

            centerlinePoint handMass fallback
        )
    ),

    fn visualArmBandTarget side center h w d z0 sideRatio zRatio fallback =
    (
        local pts = collectWorldMeshPoints (sceneModelNodes())
        local candidates = #()
        local xs = #()
        local ys = #()
        local zs = #()
        local targetSideX = w * sideRatio
        local tolerance = w * 0.045

        for p in pts do
        (
            local sx = (p.x - center.x) * side
            if abs(sx - targetSideX) <= tolerance and \
               p.y >= (center.y - d * 0.45) and p.y <= (center.y + d * 0.40) and \
               p.z >= (z0 + h * 0.28) and p.z <= (z0 + h * 0.55) do
            (
                append candidates p
                append xs p.x
                append ys p.y
                append zs p.z
            )
        )

        if candidates.count < 8 then fallback
        else
        (
            local tx = percentileValue xs 0.50 fallback.x
            local ty = percentileValue ys 0.50 fallback.y
            local tz = percentileValue zs zRatio fallback.z
            [tx, ty, tz]
        )
    ),

    fn visualArmCenterlineTarget side center h w d z0 sideRatio seedZRatio fallback =
    (
        local pts = collectWorldMeshPoints (sceneModelNodes())
        local broad = #()
        local localBand = #()
        local targetSideX = w * sideRatio
        local tolerance = w * 0.05
        local seedZ = z0 + h * seedZRatio
        local seedTolerance = h * 0.10

        for p in pts do
        (
            local sx = (p.x - center.x) * side
            if abs(sx - targetSideX) <= tolerance and \
               p.y >= (center.y - d * 0.45) and p.y <= (center.y + d * 0.40) and \
               p.z >= (z0 + h * 0.25) and p.z <= (z0 + h * 0.58) do
            (
                append broad p
                if abs(p.z - seedZ) <= seedTolerance do append localBand p
            )
        )

        if localBand.count >= 8 then centerlinePoint localBand fallback
        else if broad.count >= 8 then centerlinePoint broad fallback
        else fallback
    ),

    fn estimateGuideDefinitions bounds profile =
    (
        if guideAlgorithm != "tutorial_centerline_qbird" do
        (
            throw ("Guide algorithm '" + guideAlgorithm + "' is disabled. Use tutorial_centerline_qbird only as a visual candidate generator; legacy scoring algorithms must not be used.")
        )

        local mn = [ -35, -25, 0 ]
        local mx = [ 35, 25, defaultHeight ]

        if bounds != undefined do
        (
            mn = bounds[1]
            mx = bounds[2]
        )

        if profile == undefined do profile = analyzeBodyProfile undefined bounds

        local center = profile[4]
        local h = profile[5]
        local w = profile[6]
        local d = profile[7]

        local cx = center.x
        local cy = center.y
        local z0 = mn.z
        local waistY = if profile.count >= 42 then profile[42] else cy
        local torsoY = if profile.count >= 43 then profile[43] else cy
        local upperY = if profile.count >= 44 then profile[44] else torsoY
        local headYProfile = if profile.count >= 45 then profile[45] else upperY
        local headTopYProfile = if profile.count >= 46 then profile[46] else headYProfile
        local crestX = if profile.count >= 47 then profile[47] else cx
        local crestY = if profile.count >= 48 then profile[48] else headTopYProfile
        local legOcclusionRisk = if profile.count >= 52 then profile[52] else false
        local visualCenter = [cx, torsoY, center.z]

        local shoulderHalf = profile[17]
        local elbowHalf = profile[18]
        local wristHalf = profile[19]
        local footHalf = profile[20]
        local yArm = cy
        local yFoot = profile[21]
        local yToe = profile[22]
        local xHip = cx + footHalf * 0.90
        local legHipHalf = footHalf * 0.90
        local legKneeHalf = footHalf * 0.82
        local legAnkleHalf = footHalf
        local xShoulder = cx + shoulderHalf
        local xElbow = cx + elbowHalf
        local xWrist = cx + wristHalf
        local pelvisZ = profile[11]
        local spineZ = z0 + h * 0.46
        local hipZ = profile[12]
        local kneeZ = profile[13]
        local ankleZ = profile[14]
        local footZ = profile[15]
        local toeZ = profile[16]
        local armZ = profile[10]
        local chestZ = profile[23]
        local neckZ = profile[24]
        local headZ = profile[25]
        local headTopZ = profile[26]
        local crestTopZ = z0 + h * 0.98

        if guideAlgorithm == "bbox_humanoid" do
        (
            shoulderHalf = w * 0.30
            elbowHalf = w * 0.43
            wristHalf = w * 0.48
            footHalf = w * 0.16
            xHip = cx + w * 0.12
            xShoulder = cx + shoulderHalf
            xElbow = cx + elbowHalf
            xWrist = cx + wristHalf
            yArm = cy
            yFoot = cy - d * 0.18
            yToe = cy - d * 0.42
            pelvisZ = z0 + h * 0.43
            hipZ = z0 + h * 0.42
            kneeZ = z0 + h * 0.24
            ankleZ = z0 + h * 0.08
            footZ = z0 + h * 0.04
            toeZ = z0 + h * 0.04
            armZ = z0 + h * 0.66
            chestZ = z0 + h * 0.64
            neckZ = z0 + h * 0.74
            headZ = z0 + h * 0.84
            headTopZ = z0 + h * 0.92
            crestTopZ = z0 + h * 0.98
        )

        if guideAlgorithm == "qbird_profile" do
        (
            shoulderHalf = profile[17] * 0.92
            elbowHalf = profile[18] * 0.98
            wristHalf = profile[19] * 0.98
            footHalf = profile[20] * 0.90
            xHip = cx + footHalf * 0.70
            xShoulder = cx + shoulderHalf
            xElbow = cx + elbowHalf
            xWrist = cx + wristHalf
            pelvisZ = z0 + h * 0.39
            hipZ = z0 + h * 0.31
            kneeZ = z0 + h * 0.18
            ankleZ = z0 + h * 0.065
            footZ = z0 + h * 0.035
            toeZ = z0 + h * 0.032
            armZ = profile[10] + h * 0.015
            chestZ = z0 + h * 0.57
            neckZ = z0 + h * 0.73
            headZ = z0 + h * 0.84
            headTopZ = z0 + h * 0.92
            crestTopZ = z0 + h * 0.98
        )

        if guideAlgorithm == "semantic_qbird" do
        (
            shoulderHalf = profile[32]
            elbowHalf = profile[33]
            wristHalf = profile[34]
            footHalf = profile[35]
            yFoot = profile[36]
            yToe = profile[37]
            legHipHalf = footHalf * 0.68
            legKneeHalf = footHalf * 0.82
            legAnkleHalf = footHalf
            if legOcclusionRisk do
            (
                -- A robe/skirt can make the leg silhouette look much wider than
                -- the hidden leg chain. Keep the thigh/knee under the garment
                -- and use the visible foot mass only for the distal pivot.
                legHipHalf = footHalf * 0.42
                legKneeHalf = footHalf * 0.62
                legAnkleHalf = footHalf * 0.86
            )
            xHip = cx + legHipHalf
            xShoulder = cx + shoulderHalf
            xElbow = cx + elbowHalf
            xWrist = cx + wristHalf
            pelvisZ = z0 + h * 0.40
            hipZ = z0 + h * 0.32
            kneeZ = z0 + h * 0.175
            ankleZ = z0 + h * 0.065
            footZ = z0 + h * 0.035
            toeZ = z0 + h * 0.032
            armZ = z0 + h * profile[38]
            chestZ = z0 + h * 0.58
            neckZ = z0 + h * 0.73
            headZ = z0 + h * 0.84
            headTopZ = z0 + h * 0.98
        )

        local lClaviclePos = [cx + shoulderHalf * 0.42, yArm, armZ + h * 0.02]
        local lShoulderPos = [xShoulder, yArm, armZ]
        local lElbowPos = [xElbow, yArm, armZ - h * 0.05]
        local lWristPos = [xWrist, yArm, armZ - h * 0.10]
        local lHandPos = [xWrist, yArm, armZ - h * 0.14]
        local lHandTipPos = [xWrist + w * 0.035, yArm, armZ - h * 0.15]
        local rClaviclePos = [cx - shoulderHalf * 0.42, yArm, armZ + h * 0.02]
        local rShoulderPos = [cx - shoulderHalf, yArm, armZ]
        local rElbowPos = [cx - elbowHalf, yArm, armZ - h * 0.05]
        local rWristPos = [cx - wristHalf, yArm, armZ - h * 0.10]
        local rHandPos = [cx - wristHalf, yArm, armZ - h * 0.14]
        local rHandTipPos = [cx - wristHalf - w * 0.035, yArm, armZ - h * 0.15]
        local lHeelPos = [cx + footHalf, yFoot + d * 0.10, footZ]
        local rHeelPos = [cx - footHalf, yFoot + d * 0.10, footZ]

        if guideAlgorithm == "visual_semantic_qbird" do
        (
            shoulderHalf = profile[32]
            elbowHalf = profile[33]
            wristHalf = profile[34]
            footHalf = profile[35]
            yFoot = profile[36]
            yToe = profile[37]
            legHipHalf = footHalf * 0.68
            legKneeHalf = footHalf * 0.82
            legAnkleHalf = footHalf
            if legOcclusionRisk do
            (
                -- In the tutorial workflow this is where a rigger ignores the
                -- robe/skirt outline and keeps the leg chain under the body.
                legHipHalf = footHalf * 0.42
                legKneeHalf = footHalf * 0.62
                legAnkleHalf = footHalf * 0.86
            )
            xHip = cx + legHipHalf
            xShoulder = cx + shoulderHalf
            xElbow = cx + elbowHalf
            xWrist = cx + wristHalf
            pelvisZ = z0 + h * 0.40
            hipZ = z0 + h * 0.32
            kneeZ = z0 + h * 0.175
            ankleZ = z0 + h * 0.065
            footZ = z0 + h * 0.035
            toeZ = z0 + h * 0.032
            armZ = z0 + h * profile[38]
            chestZ = z0 + h * 0.58
            neckZ = z0 + h * 0.73
            headZ = z0 + h * 0.84
            headTopZ = z0 + h * 0.92
            crestTopZ = z0 + h * 0.98

            lClaviclePos = [cx + shoulderHalf * 0.42, yArm, armZ + h * 0.02]
            lShoulderPos = [xShoulder, yArm, armZ]
            lElbowPos = [xElbow, yArm, armZ - h * 0.05]
            rClaviclePos = [cx - shoulderHalf * 0.42, yArm, armZ + h * 0.02]
            rShoulderPos = [cx - shoulderHalf, yArm, armZ]
            rElbowPos = [cx - elbowHalf, yArm, armZ - h * 0.05]

            lHandPos = visualOuterHandTarget 1 center h w d z0 [xWrist, yArm, armZ - h * 0.14]
            rHandPos = visualOuterHandTarget -1 center h w d z0 [cx - wristHalf, yArm, armZ - h * 0.14]
            lWristPos = lElbowPos + ((lHandPos - lElbowPos) * 0.68)
            rWristPos = rElbowPos + ((rHandPos - rElbowPos) * 0.68)
        )

        if guideAlgorithm == "tutorial_visual_qbird" do
        (
            shoulderHalf = profile[32]
            elbowHalf = profile[33]
            wristHalf = profile[34]
            footHalf = profile[35]
            yFoot = profile[36]
            yToe = profile[37]
            xHip = cx + footHalf * 0.68
            xShoulder = cx + shoulderHalf
            xElbow = cx + elbowHalf
            xWrist = cx + wristHalf
            pelvisZ = z0 + h * 0.40
            hipZ = z0 + h * 0.32
            kneeZ = z0 + h * 0.175
            ankleZ = z0 + h * 0.065
            footZ = z0 + h * 0.035
            toeZ = z0 + h * 0.032
            chestZ = z0 + h * 0.58
            neckZ = z0 + h * 0.73
            headZ = z0 + h * 0.84
            headTopZ = z0 + h * 0.98

            lHandPos = visualOuterHandTarget 1 center h w d z0 [xWrist, yArm, z0 + h * 0.35]
            rHandPos = visualOuterHandTarget -1 center h w d z0 [cx - wristHalf, yArm, z0 + h * 0.35]

            lShoulderPos = visualArmBandTarget 1 center h w d z0 0.24 0.88 [cx + w * 0.24, yArm, z0 + h * 0.47]
            rShoulderPos = visualArmBandTarget -1 center h w d z0 0.24 0.88 [cx - w * 0.24, yArm, z0 + h * 0.47]
            lElbowPos = visualArmBandTarget 1 center h w d z0 0.32 0.55 [cx + w * 0.32, yArm, z0 + h * 0.39]
            rElbowPos = visualArmBandTarget -1 center h w d z0 0.32 0.55 [cx - w * 0.32, yArm, z0 + h * 0.39]
            lWristPos = visualArmBandTarget 1 center h w d z0 0.42 0.55 [cx + w * 0.42, yArm, z0 + h * 0.36]
            rWristPos = visualArmBandTarget -1 center h w d z0 0.42 0.55 [cx - w * 0.42, yArm, z0 + h * 0.36]

            if lWristPos.z < (lHandPos.z + h * 0.012) do lWristPos.z = lHandPos.z + h * 0.012
            if rWristPos.z < (rHandPos.z + h * 0.012) do rWristPos.z = rHandPos.z + h * 0.012
            if lElbowPos.z < (lWristPos.z + h * 0.025) do lElbowPos.z = lWristPos.z + h * 0.025
            if rElbowPos.z < (rWristPos.z + h * 0.025) do rElbowPos.z = rWristPos.z + h * 0.025
            if lShoulderPos.z < (lElbowPos.z + h * 0.05) do lShoulderPos.z = lElbowPos.z + h * 0.05
            if rShoulderPos.z < (rElbowPos.z + h * 0.05) do rShoulderPos.z = rElbowPos.z + h * 0.05

            lClaviclePos = [cx + ((lShoulderPos.x - cx) * 0.42), (cy + lShoulderPos.y) / 2.0, lShoulderPos.z + h * 0.035]
            rClaviclePos = [cx + ((rShoulderPos.x - cx) * 0.42), (cy + rShoulderPos.y) / 2.0, rShoulderPos.z + h * 0.035]
        )

        if guideAlgorithm == "tutorial_centerline_qbird" do
        (
            shoulderHalf = profile[32]
            elbowHalf = profile[33]
            wristHalf = profile[34]
            footHalf = profile[35]
            yFoot = profile[36]
            yToe = profile[37]
            legHipHalf = footHalf * 0.68
            legKneeHalf = footHalf * 0.82
            legAnkleHalf = footHalf
            if legOcclusionRisk do
            (
                -- In the tutorial workflow this is where a rigger ignores the
                -- robe/skirt outline and keeps the leg chain under the body.
                legHipHalf = footHalf * 0.42
                legKneeHalf = footHalf * 0.62
                legAnkleHalf = footHalf * 0.86
            )
            xHip = cx + legHipHalf
            xShoulder = cx + shoulderHalf
            xElbow = cx + elbowHalf
            xWrist = cx + wristHalf
            pelvisZ = z0 + h * 0.255
            spineZ = z0 + h * 0.365
            hipZ = z0 + h * 0.225
            kneeZ = z0 + h * 0.175
            ankleZ = z0 + h * 0.065
            footZ = z0 + h * 0.035
            toeZ = z0 + h * 0.032
            chestZ = z0 + h * 0.54
            neckZ = z0 + h * 0.665
            headZ = z0 + h * 0.755
            headTopZ = z0 + h * 0.825
            crestTopZ = z0 + h * 0.98

            local footMidY = (yFoot + yToe) / 2.0
            local heelGuideY = footMidY + d * 0.075
            local toeGuideY = footMidY - d * 0.105
            yFoot = footMidY
            yToe = toeGuideY

            local bareHeadAxisY = (upperY + headYProfile + headTopYProfile) / 3.0
            upperY = bareHeadAxisY
            headYProfile = bareHeadAxisY
            headTopYProfile = bareHeadAxisY

            yArm = torsoY
            lHandPos = visualHandCenterTarget 1 visualCenter h w d z0 [xWrist, yArm, z0 + h * 0.35]
            rHandPos = visualHandCenterTarget -1 visualCenter h w d z0 [cx - wristHalf, yArm, z0 + h * 0.35]
            lHandTipPos = visualOuterHandTarget 1 visualCenter h w d z0 [lHandPos.x + w * 0.04, lHandPos.y, lHandPos.z - h * 0.006]
            rHandTipPos = visualOuterHandTarget -1 visualCenter h w d z0 [rHandPos.x - w * 0.04, rHandPos.y, rHandPos.z - h * 0.006]
            if (distance lHandPos lHandTipPos) < (h * 0.018) do lHandTipPos = lHandPos + [w * 0.045, 0, -h * 0.006]
            if (distance rHandPos rHandTipPos) < (h * 0.018) do rHandTipPos = rHandPos + [-w * 0.045, 0, -h * 0.006]

            lShoulderPos = visualArmCenterlineTarget 1 visualCenter h w d z0 0.24 0.43 [cx + w * 0.24, yArm, z0 + h * 0.43]
            rShoulderPos = visualArmCenterlineTarget -1 visualCenter h w d z0 0.24 0.43 [cx - w * 0.24, yArm, z0 + h * 0.43]
            lElbowPos = visualArmCenterlineTarget 1 visualCenter h w d z0 0.32 0.39 [cx + w * 0.32, yArm, z0 + h * 0.39]
            rElbowPos = visualArmCenterlineTarget -1 visualCenter h w d z0 0.32 0.39 [cx - w * 0.32, yArm, z0 + h * 0.39]
            lWristPos = visualArmCenterlineTarget 1 visualCenter h w d z0 0.42 0.36 [cx + w * 0.42, yArm, z0 + h * 0.36]
            rWristPos = visualArmCenterlineTarget -1 visualCenter h w d z0 0.42 0.36 [cx - w * 0.42, yArm, z0 + h * 0.36]

            if lWristPos.z < (lHandPos.z + h * 0.008) do lWristPos.z = lHandPos.z + h * 0.008
            if rWristPos.z < (rHandPos.z + h * 0.008) do rWristPos.z = rHandPos.z + h * 0.008
            if lElbowPos.z < (lWristPos.z + h * 0.018) do lElbowPos.z = lWristPos.z + h * 0.018
            if rElbowPos.z < (rWristPos.z + h * 0.018) do rElbowPos.z = rWristPos.z + h * 0.018
            if lShoulderPos.z < (lElbowPos.z + h * 0.032) do lShoulderPos.z = lElbowPos.z + h * 0.032
            if rShoulderPos.z < (rElbowPos.z + h * 0.032) do rShoulderPos.z = rElbowPos.z + h * 0.032

            lClaviclePos = [cx + ((lShoulderPos.x - cx) * 0.42), (torsoY + lShoulderPos.y) / 2.0, lShoulderPos.z + h * 0.035]
            rClaviclePos = [cx + ((rShoulderPos.x - cx) * 0.42), (torsoY + rShoulderPos.y) / 2.0, rShoulderPos.z + h * 0.035]
            lHeelPos = [cx + legAnkleHalf, heelGuideY, footZ]
            rHeelPos = [cx - legAnkleHalf, heelGuideY, footZ]
        )

        #(
            #("Root",        [cx, waistY, pelvisZ], white),
            #("Pelvis",      [cx, waistY, pelvisZ], yellow),
            #("Spine",       [cx, ((waistY + torsoY) / 2.0), spineZ], yellow),
            #("Chest",       [cx, torsoY, chestZ], yellow),
            #("Neck",        [cx, upperY, neckZ], yellow),
            #("Head",        [cx, headYProfile, headZ], yellow),
            #("HeadTop",     [cx, headTopYProfile, headTopZ], yellow),
            #("CrestTop",    [crestX, crestY, crestTopZ], orange),

            #("L_Clavicle",  lClaviclePos, green),
            #("L_Shoulder",  lShoulderPos, green),
            #("L_Elbow",     lElbowPos, green),
            #("L_Wrist",     lWristPos, green),
            #("L_Hand",      lHandPos, green),
            #("L_HandTip",   lHandTipPos, green),
            #("L_Hip",       [cx + legHipHalf, waistY, hipZ], green),
            #("L_Knee",      [cx + legKneeHalf, ((waistY + yFoot) / 2.0), kneeZ], green),
            #("L_Ankle",     [cx + legAnkleHalf, yFoot, ankleZ], green),
            #("L_Heel",      lHeelPos, green),
            #("L_Foot",      [cx + legAnkleHalf, yFoot, footZ], green),
            #("L_Toe",       [cx + legAnkleHalf, yToe, toeZ], green),

            #("R_Clavicle",  rClaviclePos, blue),
            #("R_Shoulder",  rShoulderPos, blue),
            #("R_Elbow",     rElbowPos, blue),
            #("R_Wrist",     rWristPos, blue),
            #("R_Hand",      rHandPos, blue),
            #("R_HandTip",   rHandTipPos, blue),
            #("R_Hip",       [cx - legHipHalf, waistY, hipZ], blue),
            #("R_Knee",      [cx - legKneeHalf, ((waistY + yFoot) / 2.0), kneeZ], blue),
            #("R_Ankle",     [cx - legAnkleHalf, yFoot, ankleZ], blue),
            #("R_Heel",      rHeelPos, blue),
            #("R_Foot",      [cx - legAnkleHalf, yFoot, footZ], blue),
            #("R_Toe",       [cx - legAnkleHalf, yToe, toeZ], blue)
        )
    ),

    fn createGuidesFromSelection =
    (
        cachedEnvelopePoints = undefined
        cachedEnvelopeNodeCount = 0
        local nodes = selectedModelNodes()
        local bounds = getBounds nodes
        local profile = analyzeBodyProfile nodes bounds
        local defs = estimateGuideDefinitions bounds profile

        for def in defs do
        (
            createOrUpdateGuide def[1] def[2] def[3]
        )

        select (for def in defs where (getGuide def[1]) != undefined collect (getGuide def[1]))
        log ("Created / updated " + (defs.count as string) + " guides.")
        defs.count
    ),

    fn mirrorCenterX =
    (
        local rootGuide = getGuide "Root"
        if rootGuide != undefined then rootGuide.pos.x
        else
        (
            local bounds = getBounds (sceneModelNodes())
            if bounds != undefined then ((bounds[1].x + bounds[2].x) / 2.0) else 0.0
        )
    ),

    fn mirrorGuidePair leftName rightName =
    (
        local l = getGuide leftName
        local r = getGuide rightName

        if l == undefined then false
        else
        (
            local cx = mirrorCenterX()
            local mirroredPos = [(2.0 * cx) - l.pos.x, l.pos.y, l.pos.z]
            if r == undefined then
            (
                r = createOrUpdateGuide rightName mirroredPos blue
            )
            else
            (
                r.pos = mirroredPos
                setNodeWireColor r blue
            )
            true
        )
    ),

    fn mirrorLeftGuidesToRight =
    (
        local pairs = #(
            #("L_Clavicle", "R_Clavicle"),
            #("L_Shoulder", "R_Shoulder"),
            #("L_Elbow", "R_Elbow"),
            #("L_Wrist", "R_Wrist"),
            #("L_Hand", "R_Hand"),
            #("L_Hip", "R_Hip"),
            #("L_Knee", "R_Knee"),
            #("L_Ankle", "R_Ankle"),
            #("L_Foot", "R_Foot"),
            #("L_Toe", "R_Toe")
        )

        local count = 0
        for p in pairs do
        (
            if mirrorGuidePair p[1] p[2] do count += 1
        )

        log ("Mirrored " + (count as string) + " left guides to right guides.")
        count
    ),

    fn getGuidePosition name fallback =
    (
        local g = getGuide name
        if g == undefined then fallback else g.pos
    ),

    fn findBipedRoot =
    (
        for n in objects do
        (
            local isBip = false
            try(isBip = isProperty n.controller #figureMode)catch(isBip = false)
            if isBip do return n
        )
        undefined
    ),

    fn fitRequests =
    (
        #(
            #(#vertical, 0, "Root"),
            #(#pelvis, 0, "Pelvis"),
            #(#spine, 1, "Spine"),
            #(#spine, 2, "Chest"),
            #(#neck, 0, "Neck"),
            #(#head, 0, "Head"),

            #(#larm, 1, "L_Clavicle"),
            #(#larm, 2, "L_Shoulder"),
            #(#larm, 3, "L_Elbow"),
            #(#larm, 4, "L_Wrist"),
            #(#rarm, 1, "R_Clavicle"),
            #(#rarm, 2, "R_Shoulder"),
            #(#rarm, 3, "R_Elbow"),
            #(#rarm, 4, "R_Wrist"),

            #(#lleg, 1, "L_Hip"),
            #(#lleg, 2, "L_Knee"),
            #(#lleg, 3, "L_Ankle"),
            #(#rleg, 1, "R_Hip"),
            #(#rleg, 2, "R_Knee"),
            #(#rleg, 3, "R_Ankle"),

            #(#ltoes, 1, "L_Toe"),
            #(#rtoes, 1, "R_Toe")
        )
    ),

    fn bipedSnapshotSegments =
    (
        #(
            #("Pelvis", "Spine"),
            #("Spine", "Chest"),
            #("Chest", "Neck"),
            #("Neck", "Head"),

            #("Chest", "L_Clavicle"),
            #("L_Clavicle", "L_Shoulder"),
            #("L_Shoulder", "L_Elbow"),
            #("L_Elbow", "L_Wrist"),
            #("Chest", "R_Clavicle"),
            #("R_Clavicle", "R_Shoulder"),
            #("R_Shoulder", "R_Elbow"),
            #("R_Elbow", "R_Wrist"),

            #("Pelvis", "L_Hip"),
            #("L_Hip", "L_Knee"),
            #("L_Knee", "L_Ankle"),
            #("L_Ankle", "L_Toe"),
            #("Pelvis", "R_Hip"),
            #("R_Hip", "R_Knee"),
            #("R_Knee", "R_Ankle"),
            #("R_Ankle", "R_Toe")
        )
    ),

    fn bipedRequestForGuide guideName =
    (
        for req in fitRequests() do
        (
            if req[3] == guideName do return req
        )
        undefined
    ),

    fn templateBoneChains =
    (
        #(
            #("Pelvis", "Spine", "Chest", "Neck", "Head", "HeadTop"),
            #("Chest", "L_Clavicle", "L_Shoulder", "L_Elbow", "L_Wrist", "L_Hand", "L_HandTip"),
            #("Chest", "R_Clavicle", "R_Shoulder", "R_Elbow", "R_Wrist", "R_Hand", "R_HandTip"),
            #("Pelvis", "L_Hip", "L_Knee", "L_Ankle", "L_Heel", "L_Foot", "L_Toe"),
            #("Pelvis", "R_Hip", "R_Knee", "R_Ankle", "R_Heel", "R_Foot", "R_Toe")
        )
    ),

    fn templateBoneSegments =
    (
        local segments = #()
        for chain in templateBoneChains() do
        (
            for i = 1 to (chain.count - 1) do append segments #(chain[i], chain[i + 1])
        )
        segments
    ),

    fn templateBoneName startName endName =
    (
        "AIRA_BONE_" + startName + "_" + endName
    ),

    fn dot3 a b =
    (
        (a.x * b.x) + (a.y * b.y) + (a.z * b.z)
    ),

    fn safeBoneUpVector startPos endPos =
    (
        local direction = endPos - startPos
        local directionLength = distance startPos endPos
        if directionLength < 0.001 then [0, 1, 0]
        else
        (
            direction = direction / directionLength
            local up = [0, 0, 1]
            if (abs (dot3 direction up)) > 0.85 do up = [0, 1, 0]
            if (abs (dot3 direction up)) > 0.85 do up = [1, 0, 0]
            up
        )
    ),

    fn templateBoneRole startName endName =
    (
        if (matchPattern endName pattern:"*Toe" ignoreCase:true) or (matchPattern startName pattern:"*Foot" ignoreCase:true) then "foot"
        else if matchPattern startName pattern:"*Clavicle" ignoreCase:true or matchPattern endName pattern:"*Clavicle" ignoreCase:true then "clavicle"
        else if matchPattern startName pattern:"*Shoulder" ignoreCase:true or matchPattern startName pattern:"*Elbow" ignoreCase:true or matchPattern startName pattern:"*Wrist" ignoreCase:true then "arm"
        else if matchPattern startName pattern:"*Hip" ignoreCase:true or matchPattern startName pattern:"*Knee" ignoreCase:true or matchPattern startName pattern:"*Ankle" ignoreCase:true then "leg"
        else if matchPattern endName pattern:"*Hip" ignoreCase:true or matchPattern endName pattern:"*Knee" ignoreCase:true or matchPattern endName pattern:"*Ankle" ignoreCase:true then "leg"
        else if startName == "Root" or startName == "Pelvis" or startName == "Spine" or startName == "Chest" or startName == "Neck" or startName == "Head" then
        (
            if startName == "Head" or endName == "HeadTop" then "head" else "torso"
        )
        else "default"
    ),

    fn templateBoneSkinPolicy startName endName =
    (
        if startName == "Root" and endName == "Pelvis" then "control_only_non_deforming"
        else if startName == "HeadTop" and endName == "CrestTop" then "accessory_reference_non_deforming"
        else if matchPattern endName pattern:"*HandTip" ignoreCase:true then "hand_tip_detail_candidate"
        else if matchPattern endName pattern:"*Heel" ignoreCase:true then "side_top_foot_depth_candidate"
        else if matchPattern endName pattern:"*Toe" ignoreCase:true then "side_top_toe_pivot_candidate"
        else "deforming_candidate"
    ),

    fn envelopeSamplePoints =
    (
        local nodes = sceneModelNodes()
        if cachedEnvelopePoints == undefined or cachedEnvelopeNodeCount != nodes.count do
        (
            cachedEnvelopePoints = collectWorldMeshPoints nodes
            cachedEnvelopeNodeCount = nodes.count
        )
        cachedEnvelopePoints
    ),

    fn guideHeightSpan =
    (
        local minZ = 1e9
        local maxZ = -1e9
        local names = #(
            "Root", "Pelvis", "Spine", "Chest", "Neck", "Head", "HeadTop", "CrestTop",
            "L_Clavicle", "L_Shoulder", "L_Elbow", "L_Wrist", "L_Hand", "L_HandTip",
            "L_Hip", "L_Knee", "L_Ankle", "L_Heel", "L_Foot", "L_Toe",
            "R_Clavicle", "R_Shoulder", "R_Elbow", "R_Wrist", "R_Hand", "R_HandTip",
            "R_Hip", "R_Knee", "R_Ankle", "R_Heel", "R_Foot", "R_Toe"
        )
        for name in names do
        (
            local g = getGuide name
            if g != undefined do
            (
                if g.pos.z < minZ do minZ = g.pos.z
                if g.pos.z > maxZ do maxZ = g.pos.z
            )
        )
        if maxZ > minZ then (maxZ - minZ) else defaultHeight
    ),

    fn segmentEnvelopeThickness startPos endPos role endName baseThickness h =
    (
        local pts = envelopeSamplePoints()
        local segment = endPos - startPos
        local segmentLength = length segment
        if pts == undefined or pts.count < 16 or segmentLength < 0.001 then baseThickness
        else
        (
            local values = #()
            local maxRadius = h * 0.28
            for p in pts do
            (
                local t = (dot3 (p - startPos) segment) / (segmentLength * segmentLength)
                if t >= -0.08 and t <= 1.08 do
                (
                    local nearest = startPos + (segment * t)
                    local radius = distance p nearest
                    if radius <= maxRadius do append values radius
                )
            )
            if values.count < 12 then baseThickness
            else
            (
                local envelope = percentileValue values 0.62 baseThickness
                local factor = 0.50
                local cap = h * 0.10
                if role == "torso" do (factor = 0.62; cap = h * 0.17)
                if role == "head" do (factor = 0.58; cap = h * 0.13)
                if role == "arm" do (factor = 0.48; cap = h * 0.085)
                if role == "leg" do (factor = 0.50; cap = h * 0.09)
                if role == "foot" do (factor = 0.56; cap = h * 0.08)
                if role == "clavicle" do (factor = 0.42; cap = h * 0.075)
                if matchPattern endName pattern:"*HandTip" ignoreCase:true do (factor = 0.40; cap = h * 0.055)
                local adjusted = envelope * factor
                if adjusted < baseThickness do adjusted = baseThickness
                if adjusted > cap do adjusted = cap
                adjusted
            )
        )
    ),

    fn templateBoneThickness startName endName segmentLength =
    (
        local h = guideHeightSpan()
        local role = templateBoneRole startName endName
        local ratio = 0.028
        if role == "torso" do ratio = 0.090
        if role == "head" do ratio = 0.078
        if role == "clavicle" do ratio = 0.026
        if role == "arm" do ratio = 0.045
        if role == "leg" do ratio = 0.050
        if role == "foot" do ratio = 0.052
        if matchPattern endName pattern:"*HandTip" ignoreCase:true do ratio = 0.034
        if endName == "CrestTop" do ratio = 0.024

        local thickness = h * ratio
        local startGuide = getGuide startName
        local endGuide = getGuide endName
        if startGuide != undefined and endGuide != undefined do
        (
            thickness = segmentEnvelopeThickness startGuide.pos endGuide.pos role endName thickness h
        )
        local minThickness = guideSize * 0.18
        if thickness < minThickness do thickness = minThickness
        local lengthCapRatio = 0.55
        if role == "torso" do lengthCapRatio = 0.92
        if role == "head" do lengthCapRatio = 0.82
        if role == "foot" do lengthCapRatio = 0.70
        if role == "clavicle" do lengthCapRatio = 0.62
        if segmentLength > 0.001 and thickness > (segmentLength * lengthCapRatio) do thickness = segmentLength * lengthCapRatio
        if thickness < 0.25 do thickness = 0.25
        thickness
    ),

    fn deleteTemplateSkeleton =
    (
        local oldBones = for n in objects where matchPattern n.name pattern:"AIRA_BONE_*" ignoreCase:true collect n
        if oldBones.count > 0 do delete oldBones
        oldBones.count
    ),

    fn createTemplateBone startName endName parentBone =
    (
        local startGuide = getGuide startName
        local endGuide = getGuide endName
        if startGuide == undefined or endGuide == undefined then undefined
        else
        (
            local bone = undefined
            try
            (
                local segmentLength = distance startGuide.pos endGuide.pos
                local thickness = templateBoneThickness startName endName segmentLength
                bone = BoneSys.createBone startGuide.pos endGuide.pos [0, 1, 0]
                bone.name = templateBoneName startName endName
                bone.width = thickness
                bone.height = thickness
                bone.taper = 90
                bone.wirecolor = orange
                if parentBone != undefined do bone.parent = parentBone
                try(setUserProp bone "AIRA_Type" "TemplateBone")catch()
                try(setUserProp bone "AIRA_Role" (templateBoneRole startName endName))catch()
                try(setUserProp bone "AIRA_SkinPolicy" (templateBoneSkinPolicy startName endName))catch()
            )
            catch
            (
                log ("Failed to create template bone " + startName + " -> " + endName + ": " + (getCurrentException()))
                bone = undefined
            )
            bone
        )
    ),

    fn createTemplateBoneChain chain parentBone =
    (
        local prevBone = parentBone
        local count = 0
        for i = 1 to (chain.count - 1) do
        (
            local bone = createTemplateBone chain[i] chain[i + 1] prevBone
            if bone != undefined do
            (
                prevBone = bone
                count += 1
            )
        )
        count
    ),

    fn createTemplateSkeletonFromGuides =
    (
        local deleted = deleteTemplateSkeleton()
        log ("Template skeleton generation is disabled. Stage01 is Biped-only; deleted old AIRA_BONE nodes: " + (deleted as string))
        0
    ),

    fn setFigureMode bipRoot state =
    (
        try
        (
            bipRoot.controller.figureMode = state
            true
        )
        catch
        (
            false
        )
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

    fn bipedNodeForGuide bipRoot guideName =
    (
        local req = bipedRequestForGuide guideName
        if bipRoot == undefined or req == undefined then undefined
        else getBipedNode bipRoot req[1] req[2]
    ),

    fn getBipedNodePosition node =
    (
        local p = undefined
        try(p = biped.getTransform node #pos)catch(p = undefined)
        if p == undefined do try(p = node.transform.pos)catch(p = undefined)
        if p == undefined do try(p = node.pos)catch(p = undefined)
        p
    ),

    fn setBipedNodePosition node targetPos =
    (
        if node == undefined or targetPos == undefined then false
        else
        (
            local ok = true
            try
            (
                biped.setTransform node #pos targetPos false
            )
            catch
            (
                ok = false
            )
            if not ok do
            (
                try(node.pos = targetPos; ok = true)catch(ok = false)
            )
            ok
        )
    ),

    fn cross3 a b =
    (
        [((a.y * b.z) - (a.z * b.y)), ((a.z * b.x) - (a.x * b.z)), ((a.x * b.y) - (a.y * b.x))]
    ),

    fn safeNormalize v fallback =
    (
        local len = length v
        if len < 0.0001 then fallback else (v / len)
    ),

    fn ctSampleStations =
    (
        #(0.0, 0.25, 0.50, 0.75, 1.0)
    ),

    fn ctSectionStats pts center axis uAxis vAxis slab h =
    (
        local us = #()
        local vs = #()
        local sectors = #()
        for p in pts do
        (
            local delta = p - center
            if (abs (dot3 delta axis)) <= slab do
            (
                local u = dot3 delta uAxis
                local v = dot3 delta vAxis
                append us u
                append vs v
                local radius = sqrt ((u * u) + (v * v))
                if radius > 0.00001 do
                (
                    local angle = atan2 v u
                    if angle < 0.0 do angle += 360.0
                    local sector = ((floor (angle / (360.0 / ctWrapSectorCount))) as integer) + 1
                    if sector < 1 do sector = 1
                    if sector > ctWrapSectorCount do sector = ctWrapSectorCount
                    if (findItem sectors sector) == 0 do append sectors sector
                )
            )
        )

        if us.count < 12 then
        (
            #(false, us.count, 0.0, 0.0, 0.0, "insufficient_slice_points", 0.0, 0)
        )
        else
        (
            local minU = 1e9
            local maxU = -1e9
            local minV = 1e9
            local maxV = -1e9
            local q1 = false
            local q2 = false
            local q3 = false
            local q4 = false
            for i = 1 to us.count do
            (
                local u = us[i]
                local v = vs[i]
                if u < minU do minU = u
                if u > maxU do maxU = u
                if v < minV do minV = v
                if v > maxV do maxV = v
                if u >= 0.0 and v >= 0.0 do q1 = true
                if u < 0.0 and v >= 0.0 do q2 = true
                if u < 0.0 and v < 0.0 do q3 = true
                if u >= 0.0 and v < 0.0 do q4 = true
            )
            local quadrantCount = 0
            if q1 do quadrantCount += 1
            if q2 do quadrantCount += 1
            if q3 do quadrantCount += 1
            if q4 do quadrantCount += 1
            local axisContainsCenter = (minU <= 0.0 and maxU >= 0.0 and minV <= 0.0 and maxV >= 0.0)
            local quadrantWrap = quadrantCount >= 4
            local sectorCoverage = (sectors.count as float) / (ctWrapSectorCount as float)
            local uCenter = ((percentileValue us 0.12 0.0) + (percentileValue us 0.88 0.0)) / 2.0
            local vCenter = ((percentileValue vs 0.12 0.0) + (percentileValue vs 0.88 0.0)) / 2.0
            local offsetLen = length [uCenter, vCenter, 0.0]
            local sectorWrap = sectorCoverage >= ctWrapMinSectorCoverage
            local ok = axisContainsCenter and quadrantWrap and sectorWrap
            local state = if ok then "strictly_wrapped" else (if not axisContainsCenter then "center_outside_axis_range" else (if not quadrantWrap then "insufficient_radial_quadrants" else "insufficient_radial_sector_coverage"))
            #(ok, us.count, uCenter, vCenter, (if ok then 0.0 else offsetLen), state, sectorCoverage, quadrantCount)
        )
    ),

    fn ctSegmentDiagnostics bipRoot seg pts h =
    (
        local startNode = bipedNodeForGuide bipRoot seg[1]
        local endNode = bipedNodeForGuide bipRoot seg[2]
        local startPos = if startNode != undefined then getBipedNodePosition startNode else undefined
        local endPos = if endNode != undefined then getBipedNodePosition endNode else undefined
        local stations = ctSampleStations()
        if startPos == undefined or endPos == undefined then #(stations.count, 0.0, 0, #((seg[1] as string) + "->" + (seg[2] as string)))
        else
        (
            local axisVec = endPos - startPos
            local segLen = length axisVec
            if segLen < 0.001 then #(stations.count, 0.0, 0, #((seg[1] as string) + "->" + (seg[2] as string) + " zero_length"))
            else
            (
                local axis = safeNormalize axisVec [0, 0, 1]
                local ref = [0, 0, 1]
                if (abs (dot3 axis ref)) > 0.86 do ref = [1, 0, 0]
                local uAxis = safeNormalize (cross3 axis ref) [1, 0, 0]
                local vAxis = safeNormalize (cross3 axis uAxis) [0, 1, 0]
                local slab = h * 0.018
                if (segLen * 0.100) > slab do slab = segLen * 0.100
                if slab < 1.0 do slab = 1.0

                local failures = 0
                local maxOffset = 0.0
                local samples = 0
                local missing = #()
                for t in stations do
                (
                    local center = startPos + (axisVec * t)
                    local stats = ctSectionStats pts center axis uAxis vAxis slab h
                    samples += 1
                    if stats[5] > maxOffset do maxOffset = stats[5]
                    if not stats[1] do failures += 1
                )
                #(failures, maxOffset, samples, missing)
            )
        )
    ),

    fn ctVolumeDiagnosticsFromSamples bipRoot pts h =
    (
        local failures = 0
        local maxOffset = 0.0
        local samples = 0
        local missing = #()
        local stations = ctSampleStations()

        if pts == undefined or pts.count < 16 then
        (
            #(9999, 0.0, 0, #("insufficient_mesh_points"))
        )
        else
        (
            for seg in bipedSnapshotSegments() do
            (
                local diag = ctSegmentDiagnostics bipRoot seg pts h
                failures += diag[1]
                if diag[2] > maxOffset do maxOffset = diag[2]
                samples += diag[3]
                for item in diag[4] do append missing item
            )
            #(failures, maxOffset, samples, missing)
        )
    ),

    fn ctVolumeDiagnostics bipRoot =
    (
        local pts = envelopeSamplePoints()
        local h = guideHeightSpan()
        if h <= 1.0 do h = defaultHeight
        ctVolumeDiagnosticsFromSamples bipRoot pts h
    ),

    fn clampVectorStep vec maxStep =
    (
        local len = length vec
        if len > maxStep and len > 0.0001 then (vec * (maxStep / len)) else vec
    ),

    fn ctRefineSegment bipRoot seg pts h =
    (
        local startNode = bipedNodeForGuide bipRoot seg[1]
        local endNode = bipedNodeForGuide bipRoot seg[2]
        local startPos = if startNode != undefined then getBipedNodePosition startNode else undefined
        local endPos = if endNode != undefined then getBipedNodePosition endNode else undefined
        if startPos == undefined or endPos == undefined then #(0, 0, 0.0)
        else
        (
            local axisVec = endPos - startPos
            local segLen = length axisVec
            if segLen < 0.001 then #(0, 0, 0.0)
            else
            (
                local axis = safeNormalize axisVec [0, 0, 1]
                local ref = [0, 0, 1]
                if (abs (dot3 axis ref)) > 0.86 do ref = [1, 0, 0]
                local uAxis = safeNormalize (cross3 axis ref) [1, 0, 0]
                local vAxis = safeNormalize (cross3 axis uAxis) [0, 1, 0]
                local slab = h * 0.018
                if (segLen * 0.100) > slab do slab = segLen * 0.100
                if slab < 1.0 do slab = 1.0

                local startAccum = [0, 0, 0]
                local endAccum = [0, 0, 0]
                local startWeight = 0.0
                local endWeight = 0.0
                local correctedSamples = 0
                local maxOffset = 0.0
                local tolerance = h * ctWrapToleranceRatio
                local maxStep = h * ctWrapMaxStepRatio
                if (segLen * 0.35) < maxStep do maxStep = segLen * 0.35
                local stations = ctSampleStations()

                for t in stations do
                (
                    local center = startPos + (axisVec * t)
                    local stats = ctSectionStats pts center axis uAxis vAxis slab h
                    if stats[5] > maxOffset do maxOffset = stats[5]
                    if (not stats[1]) and stats[2] >= 12 and stats[5] > tolerance do
                    (
                        local offset = (uAxis * stats[3]) + (vAxis * stats[4])
                        offset = clampVectorStep offset maxStep
                        local sw = 1.0 - t
                        local ew = t
                        if t <= 0.001 do (sw = 1.0; ew = 0.0)
                        if t >= 0.999 do (sw = 0.0; ew = 1.0)
                        if sw > 0.0 do
                        (
                            startAccum += offset * sw
                            startWeight += sw
                        )
                        if ew > 0.0 do
                        (
                            endAccum += offset * ew
                            endWeight += ew
                        )
                        correctedSamples += 1
                    )
                )

                local moved = 0
                if startWeight > 0.0 do
                (
                    local move = (startAccum * (1.0 / startWeight)) * ctWrapDamping
                    move = clampVectorStep move maxStep
                    if setBipedNodePosition startNode (startPos + move) do moved += 1
                )
                if endWeight > 0.0 do
                (
                    local move = (endAccum * (1.0 / endWeight)) * ctWrapDamping
                    move = clampVectorStep move maxStep
                    if setBipedNodePosition endNode (endPos + move) do moved += 1
                )
                #(moved, correctedSamples, maxOffset)
            )
        )
    ),

    fn orderedCtRefineSegments =
    (
        #(
            #("Pelvis", "Spine"),
            #("Pelvis", "L_Hip"),
            #("L_Hip", "L_Knee"),
            #("L_Knee", "L_Ankle"),
            #("L_Ankle", "L_Toe"),
            #("Pelvis", "R_Hip"),
            #("R_Hip", "R_Knee"),
            #("R_Knee", "R_Ankle"),
            #("R_Ankle", "R_Toe"),
            #("Spine", "Chest"),
            #("Chest", "Neck"),
            #("Neck", "Head"),
            #("Chest", "L_Clavicle"),
            #("L_Clavicle", "L_Shoulder"),
            #("L_Shoulder", "L_Elbow"),
            #("L_Elbow", "L_Wrist"),
            #("Chest", "R_Clavicle"),
            #("R_Clavicle", "R_Shoulder"),
            #("R_Shoulder", "R_Elbow"),
            #("R_Elbow", "R_Wrist")
        )
    ),

    fn ctLockedFailureCount bipRoot lockedSegments pts h =
    (
        local failures = 0
        for seg in lockedSegments do
        (
            local diag = ctSegmentDiagnostics bipRoot seg pts h
            failures += diag[1]
        )
        failures
    ),

    fn ctSegmentsShareNode a b =
    (
        (a[1] == b[1]) or (a[1] == b[2]) or (a[2] == b[1]) or (a[2] == b[2])
    ),

    fn ctRelatedFailureCount bipRoot activeSeg pts h =
    (
        local failures = 0
        for seg in orderedCtRefineSegments() do
        (
            if ctSegmentsShareNode seg activeSeg do
            (
                local diag = ctSegmentDiagnostics bipRoot seg pts h
                failures += diag[1]
            )
        )
        failures
    ),

    fn ctCaptureBipedPositions bipRoot =
    (
        local positions = #()
        if bipRoot != undefined do
        (
            for req in fitRequests() do
            (
                local node = getBipedNode bipRoot req[1] req[2]
                local pos = if node != undefined then getBipedNodePosition node else undefined
                if pos != undefined do append positions #(req[3], pos)
            )
        )
        positions
    ),

    fn ctRestoreBipedPositions bipRoot positions =
    (
        local restored = 0
        if bipRoot != undefined and positions != undefined do
        (
            for item in positions do
            (
                local node = bipedNodeForGuide bipRoot item[1]
                if node != undefined and setBipedNodePosition node item[2] do restored += 1
            )
        )
        restored
    ),

    fn ctRefineSegmentEndOnly bipRoot seg pts h =
    (
        local startNode = bipedNodeForGuide bipRoot seg[1]
        local endNode = bipedNodeForGuide bipRoot seg[2]
        local startPos = if startNode != undefined then getBipedNodePosition startNode else undefined
        local endPos = if endNode != undefined then getBipedNodePosition endNode else undefined
        if startPos == undefined or endPos == undefined then #(0, 0, 0.0)
        else
        (
            local axisVec = endPos - startPos
            local segLen = length axisVec
            if segLen < 0.001 then #(0, 0, 0.0)
            else
            (
                local axis = safeNormalize axisVec [0, 0, 1]
                local ref = [0, 0, 1]
                if (abs (dot3 axis ref)) > 0.86 do ref = [1, 0, 0]
                local uAxis = safeNormalize (cross3 axis ref) [1, 0, 0]
                local vAxis = safeNormalize (cross3 axis uAxis) [0, 1, 0]
                local slab = h * 0.018
                if (segLen * 0.100) > slab do slab = segLen * 0.100
                if slab < 1.0 do slab = 1.0

                local endAccum = [0, 0, 0]
                local endWeight = 0.0
                local correctedSamples = 0
                local maxOffset = 0.0
                local tolerance = h * ctWrapToleranceRatio
                local maxStep = h * ctWrapMaxStepRatio
                if (segLen * 0.35) < maxStep do maxStep = segLen * 0.35
                local stations = ctSampleStations()

                for t in stations do
                (
                    local center = startPos + (axisVec * t)
                    local stats = ctSectionStats pts center axis uAxis vAxis slab h
                    if stats[5] > maxOffset do maxOffset = stats[5]
                    if t > 0.001 and (not stats[1]) and stats[2] >= 12 and stats[5] > tolerance do
                    (
                        local influence = t
                        if influence < 0.20 do influence = 0.20
                        local offset = ((uAxis * stats[3]) + (vAxis * stats[4])) * (1.0 / influence)
                        offset = clampVectorStep offset maxStep
                        endAccum += offset
                        endWeight += 1.0
                        correctedSamples += 1
                    )
                )

                local moved = 0
                if endWeight > 0.0 do
                (
                    local move = (endAccum * (1.0 / endWeight)) * ctWrapDamping
                    move = clampVectorStep move maxStep
                    if setBipedNodePosition endNode (endPos + move) do moved += 1
                )
                #(moved, correctedSamples, maxOffset)
            )
        )
    ),

    fn ctAppendCandidateMove moves move =
    (
        if move != undefined and (length move) > 0.0001 do append moves move
    ),

    fn ctCandidateMovesForNode bipRoot seg moveGuideName pts h maxStep =
    (
        local moves = #()
        local startNode = bipedNodeForGuide bipRoot seg[1]
        local endNode = bipedNodeForGuide bipRoot seg[2]
        local startPos = if startNode != undefined then getBipedNodePosition startNode else undefined
        local endPos = if endNode != undefined then getBipedNodePosition endNode else undefined
        if startPos != undefined and endPos != undefined do
        (
            local axisVec = endPos - startPos
            local segLen = length axisVec
            if segLen > 0.001 do
            (
                local axis = safeNormalize axisVec [0, 0, 1]
                local ref = [0, 0, 1]
                if (abs (dot3 axis ref)) > 0.86 do ref = [1, 0, 0]
                local uAxis = safeNormalize (cross3 axis ref) [1, 0, 0]
                local vAxis = safeNormalize (cross3 axis uAxis) [0, 1, 0]
                local slab = h * 0.018
                if (segLen * 0.100) > slab do slab = segLen * 0.100
                if slab < 1.0 do slab = 1.0
                local stations = ctSampleStations()

                for t in stations do
                (
                    local center = startPos + (axisVec * t)
                    local stats = ctSectionStats pts center axis uAxis vAxis slab h
                    if (not stats[1]) and stats[2] >= 12 and stats[5] > (h * ctWrapToleranceRatio) do
                    (
                        local influence = if moveGuideName == seg[2] then t else (1.0 - t)
                        if influence < 0.25 do influence = 0.25
                        local offset = ((uAxis * stats[3]) + (vAxis * stats[4])) * (1.0 / influence)
                        offset = clampVectorStep offset maxStep
                        ctAppendCandidateMove moves offset
                        ctAppendCandidateMove moves (offset * 0.5)
                        ctAppendCandidateMove moves (offset * 0.25)
                    )
                )
            )
        )

        for fraction in #(0.25, 0.50, 1.0) do
        (
            ctAppendCandidateMove moves ([1, 0, 0] * maxStep * fraction)
            ctAppendCandidateMove moves ([-1, 0, 0] * maxStep * fraction)
            ctAppendCandidateMove moves ([0, 1, 0] * maxStep * fraction)
            ctAppendCandidateMove moves ([0, -1, 0] * maxStep * fraction)
            ctAppendCandidateMove moves ([0, 0, 1] * maxStep * fraction)
            ctAppendCandidateMove moves ([0, 0, -1] * maxStep * fraction)
        )
        moves
    ),

    fn ctScoreSegment bipRoot seg lockedSegments pts h =
    (
        local activeDiag = ctSegmentDiagnostics bipRoot seg pts h
        local lockedFailures = ctLockedFailureCount bipRoot lockedSegments pts h
        local relatedFailures = ctRelatedFailureCount bipRoot seg pts h
        #(activeDiag[1], lockedFailures, relatedFailures, 0, activeDiag[2])
    ),

    fn ctTrialScoreBetter trialScore bestScore =
    (
        (trialScore[1] < bestScore[1]) or \
        (trialScore[1] == bestScore[1] and trialScore[3] < bestScore[3]) or \
        (trialScore[1] == bestScore[1] and trialScore[3] == bestScore[3] and trialScore[5] < bestScore[5])
    ),

    fn ctVolumeDiagBetter trialDiag bestDiag =
    (
        (trialDiag[1] < bestDiag[1]) or \
        (trialDiag[1] == bestDiag[1] and trialDiag[2] < bestDiag[2])
    ),

    fn ctRefineSegmentCandidateSearch bipRoot seg lockedSegments pts h maxSegmentIterations allowStartBacktrack =
    (
        local maxStep = h * ctWrapMaxStepRatio
        local startNode = bipedNodeForGuide bipRoot seg[1]
        local endNode = bipedNodeForGuide bipRoot seg[2]
        local startPos = if startNode != undefined then getBipedNodePosition startNode else undefined
        local endPos = if endNode != undefined then getBipedNodePosition endNode else undefined
        if startPos != undefined and endPos != undefined do
        (
            local segLen = distance startPos endPos
            if (segLen * 0.35) < maxStep do maxStep = segLen * 0.35
        )
        if maxStep < 0.25 do maxStep = 0.25

        local beforeScore = ctScoreSegment bipRoot seg lockedSegments pts h
        local currentScore = beforeScore
        local acceptedMoves = 0
        local iterations = 0
        local stopReason = if currentScore[1] == 0 then "already_green" else "no_positive_candidate"

        for localIter = 1 to maxSegmentIterations while currentScore[1] > 0 do
        (
            local bestScore = currentScore
            local bestMove = undefined
            local bestGuideName = ""
            local moveGuides = #(seg[2])
            if allowStartBacktrack do append moveGuides seg[1]

            for guideName in moveGuides do
            (
                local node = bipedNodeForGuide bipRoot guideName
                local oldPos = if node != undefined then getBipedNodePosition node else undefined
                if oldPos != undefined do
                (
                    for move in (ctCandidateMovesForNode bipRoot seg guideName pts h maxStep) do
                    (
                        if setBipedNodePosition node (oldPos + move) do
                        (
                            local trialScore = ctScoreSegment bipRoot seg lockedSegments pts h
                            if trialScore[2] <= currentScore[2] and trialScore[3] <= currentScore[3] and (ctTrialScoreBetter trialScore bestScore) do
                            (
                                bestScore = trialScore
                                bestMove = move
                                bestGuideName = guideName
                            )
                            setBipedNodePosition node oldPos
                        )
                    )
                )
            )

            if bestMove == undefined then
            (
                stopReason = "no_positive_candidate"
                exit
            )
            else
            (
                local bestNode = bipedNodeForGuide bipRoot bestGuideName
                local bestOldPos = if bestNode != undefined then getBipedNodePosition bestNode else undefined
                if bestOldPos == undefined then
                (
                    stopReason = "missing_candidate_node"
                    exit
                )
                else
                (
                    setBipedNodePosition bestNode (bestOldPos + bestMove)
                    currentScore = bestScore
                    iterations = localIter
                    acceptedMoves += 1
                    stopReason = if currentScore[1] == 0 then "segment_green" else "improving"
                )
            )
        )
        #(beforeScore, currentScore, iterations, acceptedMoves, stopReason)
    ),

    fn ctLegacyGlobalRefine bipRoot pts h maxIterations traceItems =
    (
        local diag = ctVolumeDiagnostics bipRoot
        local iterations = 0
        local converged = (diag[1] == 0)
        local previousMetric = diag[1] * 100000.0 + diag[2]
        for i = 1 to maxIterations while not converged do
        (
            local movedNodes = 0
            local correctedSamples = 0
            local maxSegmentOffset = 0.0
            for seg in bipedSnapshotSegments() do
            (
                local segResult = ctRefineSegment bipRoot seg pts h
                movedNodes += segResult[1]
                correctedSamples += segResult[2]
                if segResult[3] > maxSegmentOffset do maxSegmentOffset = segResult[3]
            )
            diag = ctVolumeDiagnostics bipRoot
            iterations = i
            local failureCount = diag[1]
            local maxDistance = diag[2]
            local metric = failureCount * 100000.0 + maxDistance
            append traceItems ("legacy iter " + (i as string) + " ctMovedNodes=" + (movedNodes as string) + ", ctCorrectedSamples=" + (correctedSamples as string) + ", ctFailures=" + (failureCount as string) + ", maxCtOffset=" + (maxDistance as string) + ", maxSegmentOffset=" + (maxSegmentOffset as string))
            converged = (failureCount == 0)
            if (not converged) and i > 3 and metric >= previousMetric and correctedSamples == 0 do exit
            previousMetric = metric
        )
        #(diag, iterations, converged)
    ),

    fn syncGuidesToBiped bipRoot =
    (
        local count = 0
        if bipRoot != undefined do
        (
            for req in fitRequests() do
            (
                local node = getBipedNode bipRoot req[1] req[2]
                local guide = getGuide req[3]
                local nodePos = if node != undefined then getBipedNodePosition node else undefined
                if guide != undefined and nodePos != undefined do
                (
                    guide.pos = nodePos
                    count += 1
                )
            )
        )
        count
    ),

    fn setBipedNodeToGuide bipRoot limbName linkIndex guideName =
    (
        local node = getBipedNode bipRoot limbName linkIndex
        local guide = getGuide guideName

        if node == undefined or guide == undefined then false
        else setBipedNodePosition node guide.pos
    ),

    fn setBipedGuideName bipRoot guideName =
    (
        local req = bipedRequestForGuide guideName
        if req == undefined then false
        else setBipedNodeToGuide bipRoot req[1] req[2] req[3]
    ),

    fn fitGuideOrder =
    (
        #(
            "Root", "Pelvis", "Spine", "Chest", "Neck", "Head",
            "L_Clavicle", "L_Shoulder", "L_Elbow", "L_Wrist",
            "R_Clavicle", "R_Shoulder", "R_Elbow", "R_Wrist",
            "L_Hip", "L_Knee", "L_Ankle",
            "R_Hip", "R_Knee", "R_Ankle",
            "L_Toe", "R_Toe"
        )
    ),

    fn fitBipedGuideOrder bipRoot guideNames =
    (
        local count = 0
        for guideName in guideNames do
        (
            if setBipedGuideName bipRoot guideName do count += 1
        )
        count
    ),

    fn fitDiagnostics bipRoot =
    (
        local modelNodes = sceneModelNodes()
        local bounds = getBounds modelNodes
        local h = guideHeightSpan()
        if h <= 1.0 do h = defaultHeight
        local tolerance = h * fitToleranceRatio
        if tolerance < minFitTolerance do tolerance = minFitTolerance
        local margin = [h * 0.12, h * 0.20, h * 0.08]
        local fitFailures = #()
        local failedGuides = #()
        local missingSamples = #()
        local outsideSamples = #()
        local totalDistance = 0.0
        local maxDistance = 0.0
        local sampleCount = 0

        if bipRoot != undefined do
        (
            for req in fitRequests() do
            (
                local node = getBipedNode bipRoot req[1] req[2]
                local guide = getGuide req[3]
                if node == undefined or guide == undefined then
                (
                    append missingSamples ((req[3] as string) + " -> " + (req[1] as string) + "[" + (req[2] as string) + "]")
                    append failedGuides req[3]
                )
                else
                (
                    local nodePos = getBipedNodePosition node
                    if nodePos == undefined then
                    (
                        append missingSamples ((req[3] as string) + " -> could not read Biped node position")
                        append failedGuides req[3]
                    )
                    else
                    (
                        local d = 0.0
                        try(d = distance nodePos guide.pos)catch(d = 999999.0)
                        sampleCount += 1
                        totalDistance += d
                        if d > maxDistance do maxDistance = d
                        if d > tolerance do
                        (
                            append fitFailures (req[3] + " distance=" + (d as string) + ", tolerance=" + (tolerance as string))
                            append failedGuides req[3]
                        )
                        if bounds != undefined do
                        (
                            local mn = bounds[1] - margin
                            local mx = bounds[2] + margin
                            if not (nodePos.x >= mn.x and nodePos.x <= mx.x and nodePos.y >= mn.y and nodePos.y <= mx.y and nodePos.z >= mn.z and nodePos.z <= mx.z) do append outsideSamples (node.name + " outside expanded model bounds at " + (nodePos as string))
                        )
                    )
                )
            )
        )

        local avgDistance = if sampleCount > 0 then totalDistance / sampleCount else 0.0
        #(fitFailures, failedGuides, missingSamples, outsideSamples, totalDistance, maxDistance, sampleCount, tolerance, avgDistance)
    ),

    fn uniqueGuideNames names =
    (
        local out = #()
        for name in names do
        (
            if findItem out name == 0 do append out name
        )
        out
    ),

    fn expandFitContext failedGuides =
    (
        local out = #()
        for name in failedGuides do
        (
            append out name
            if name == "Chest" do
            (
                append out "Spine"
                append out "Neck"
            )
            if matchPattern name pattern:"L_*" ignoreCase:true do
            (
                if matchPattern name pattern:"L_Shoulder" ignoreCase:true or matchPattern name pattern:"L_Elbow" ignoreCase:true or matchPattern name pattern:"L_Wrist" ignoreCase:true do
                (
                    append out "L_Clavicle"
                    append out "L_Wrist"
                    append out "L_Shoulder"
                    append out "L_Elbow"
                )
                if matchPattern name pattern:"L_Hip" ignoreCase:true or matchPattern name pattern:"L_Knee" ignoreCase:true or matchPattern name pattern:"L_Ankle" ignoreCase:true or matchPattern name pattern:"L_Toe" ignoreCase:true do
                (
                    append out "Pelvis"
                    append out "L_Ankle"
                    append out "L_Toe"
                    append out "L_Hip"
                    append out "L_Knee"
                )
            )
            if matchPattern name pattern:"R_*" ignoreCase:true do
            (
                if matchPattern name pattern:"R_Shoulder" ignoreCase:true or matchPattern name pattern:"R_Elbow" ignoreCase:true or matchPattern name pattern:"R_Wrist" ignoreCase:true do
                (
                    append out "R_Clavicle"
                    append out "R_Wrist"
                    append out "R_Shoulder"
                    append out "R_Elbow"
                )
                if matchPattern name pattern:"R_Hip" ignoreCase:true or matchPattern name pattern:"R_Knee" ignoreCase:true or matchPattern name pattern:"R_Ankle" ignoreCase:true or matchPattern name pattern:"R_Toe" ignoreCase:true do
                (
                    append out "Pelvis"
                    append out "R_Ankle"
                    append out "R_Toe"
                    append out "R_Hip"
                    append out "R_Knee"
                )
            )
        )
        uniqueGuideNames out
    ),

    fn orderedFitContext failedGuides =
    (
        local context = expandFitContext failedGuides
        local ordered = #()
        local fullOrder = fitGuideOrder()
        for name in fullOrder do
        (
            if findItem context name > 0 do append ordered name
        )
        if ordered.count == 0 then fullOrder else ordered
    ),

    fn scaledValue value minValue maxValue =
    (
        local out = value
        if out < minValue do out = minValue
        if out > maxValue do out = maxValue
        out
    ),

    fn scaleBipedSegmentTowardGuides bipRoot startGuideName endGuideName scaleGuideName =
    (
        local startNode = bipedNodeForGuide bipRoot startGuideName
        local endNode = bipedNodeForGuide bipRoot endGuideName
        local scaleNode = bipedNodeForGuide bipRoot scaleGuideName
        local startGuide = getGuide startGuideName
        local endGuide = getGuide endGuideName
        if startNode == undefined or endNode == undefined or scaleNode == undefined or startGuide == undefined or endGuide == undefined then false
        else
        (
            local startPos = getBipedNodePosition startNode
            local endPos = getBipedNodePosition endNode
            if startPos == undefined or endPos == undefined then false
            else
            (
                local currentLength = distance startPos endPos
                local targetLength = distance startGuide.pos endGuide.pos
                if currentLength < 0.001 or targetLength < 0.001 then false
                else
                (
                    local ratio = targetLength / currentLength
                    if ratio < 0.05 do ratio = 0.05
                    if ratio > 8.0 do ratio = 8.0
                    if abs(ratio - 1.0) < 0.015 then false
                    else
                    (
                        local currentScale = undefined
                        try(currentScale = biped.getTransform scaleNode #scale)catch(currentScale = undefined)
                        if currentScale == undefined do currentScale = [1, 1, 1]
                        local newScale = [scaledValue (currentScale.x * ratio) 0.05 30.0, currentScale.y, currentScale.z]
                        local ok = true
                        try(biped.setTransform scaleNode #scale newScale false)catch(ok = false)
                        ok
                    )
                )
            )
        )
    ),

    fn scaleBipedSegmentsToGuides bipRoot =
    (
        local count = 0
        local segments = #(
            #("Pelvis", "Spine", "Pelvis"),
            #("Spine", "Chest", "Spine"),
            #("Chest", "Neck", "Chest"),
            #("Neck", "Head", "Neck"),
            #("L_Clavicle", "L_Shoulder", "L_Clavicle"),
            #("L_Shoulder", "L_Elbow", "L_Shoulder"),
            #("L_Elbow", "L_Wrist", "L_Elbow"),
            #("R_Clavicle", "R_Shoulder", "R_Clavicle"),
            #("R_Shoulder", "R_Elbow", "R_Shoulder"),
            #("R_Elbow", "R_Wrist", "R_Elbow"),
            #("Pelvis", "L_Hip", "Pelvis"),
            #("L_Hip", "L_Knee", "L_Hip"),
            #("L_Knee", "L_Ankle", "L_Knee"),
            #("Pelvis", "R_Hip", "Pelvis"),
            #("R_Hip", "R_Knee", "R_Hip"),
            #("R_Knee", "R_Ankle", "R_Knee"),
            #("L_Ankle", "L_Toe", "L_Ankle"),
            #("R_Ankle", "R_Toe", "R_Ankle")
        )
        for seg in segments do
        (
            if scaleBipedSegmentTowardGuides bipRoot seg[1] seg[2] seg[3] do count += 1
        )
        count
    ),

    fn guideHeight =
    (
        local h = guideHeightSpan()
        if h > 1.0 then h else defaultHeight
    ),

    fn bipedStructureForCurrentModel =
    (
        local bodyType = "unknown"
        local handDetail = "four_finger_tutorial_default"
        local fingers = 4
        local fingerLinks = 3
        local spineLinks = 2
        local neckLinks = 1
        local legLinks = 3
        local toes = 1
        local toeLinks = 1
        local ankleAttach = 0.2

        local nodes = sceneModelNodes()
        local bounds = getBounds nodes
        if bounds != undefined do
        (
            local profile = analyzeBodyProfile nodes bounds
            bodyType = profile[27]
        )

        if bodyType == "compact_q_bird_wide_body_short_legs" do
        (
            -- The current A1 Q-bird/Luxun mesh has compact mitten-like hands in
            -- the silhouette pass. Keep the hand as a single controllable mass
            -- until explicit finger landmarks are available.
            fingers = 0
            fingerLinks = 1
            handDetail = "single_hand_mass_no_finger_landmarks"
        )

        #(bodyType, spineLinks, neckLinks, legLinks, fingers, fingerLinks, toes, toeLinks, ankleAttach, handDetail)
    ),

    fn createBipedFromGuides =
    (
        local h = guideHeight()
        local rootPos = getGuidePosition "Pelvis" [0, 0, h * 0.43]
        local structure = bipedStructureForCurrentModel()
        local bodyType = structure[1]
        local spineLinks = structure[2]
        local neckLinks = structure[3]
        local legLinks = structure[4]
        local fingers = structure[5]
        local fingerLinks = structure[6]
        local toes = structure[7]
        local toeLinks = structure[8]
        local ankleAttach = structure[9]

        local bipRoot = undefined
        try
        (
            bipRoot = biped.createNew h facingAngle rootPos \
                arms:true neckLinks:neckLinks spineLinks:spineLinks legLinks:legLinks \
                fingers:fingers fingerLinks:fingerLinks toes:toes toeLinks:toeLinks \
                ankleAttach:ankleAttach trianglePelvis:true
        )
        catch
        (
            if fingers == 0 then
            (
                try
                (
                    fingers = 4
                    fingerLinks = 3
                    bipRoot = biped.createNew h facingAngle rootPos \
                        arms:true neckLinks:neckLinks spineLinks:spineLinks legLinks:legLinks \
                        fingers:fingers fingerLinks:fingerLinks toes:toes toeLinks:toeLinks \
                        ankleAttach:ankleAttach trianglePelvis:true
                )
                catch
                (
                    bipRoot = undefined
                )
            )
            if bipRoot == undefined do
            (
                messageBox "Could not create Biped. Make sure Character Studio / Biped is available." title:"AIRA Stage01"
                return undefined
            )
        )

        try(bipRoot.name = bipedName)catch()
        try(setUserProp bipRoot "AIRA_BodyType" bodyType)catch()
        try(setUserProp bipRoot "AIRA_Fingers" (fingers as string))catch()
        AIRA_Stage01.fitBipedToGuides bipRoot
        select bipRoot
        log ("Created Biped with height " + (h as string) + ", bodyType=" + bodyType + ", fingers=" + (fingers as string) + ".")
        bipRoot
    ),

    fn fitBipedToGuides bipRoot =
    (
        if bipRoot == undefined do bipRoot = findBipedRoot()
        if bipRoot == undefined then
        (
            messageBox "No Biped root found. Create a Biped first." title:"AIRA Stage01"
            return false
        )

        setFigureMode bipRoot true

        local count = fitBipedGuideOrder bipRoot (fitGuideOrder())

        log ("Fit " + (count as string) + " Biped nodes to guides. Please inspect and fine tune in Figure Mode.")
        true
    ),

    fn getUserPropStringSafe node propName defaultValue =
    (
        local value = undefined
        try(value = getUserProp node propName)catch(value = undefined)
        if value == undefined then defaultValue else (value as string)
    ),

    fn setFitRefineProps bipRoot mode maxIterations iterations initialFailures finalFailures initialMax finalMax converged trace =
    (
        try(setUserProp bipRoot "AIRA_FitRefineMode" mode)catch()
        try(setUserProp bipRoot "AIRA_FitRefineMaxIterations" (maxIterations as string))catch()
        try(setUserProp bipRoot "AIRA_FitRefineIterations" (iterations as string))catch()
        try(setUserProp bipRoot "AIRA_FitRefineInitialFailures" (initialFailures as string))catch()
        try(setUserProp bipRoot "AIRA_FitRefineFinalFailures" (finalFailures as string))catch()
        try(setUserProp bipRoot "AIRA_FitRefineInitialMaxDistance" (initialMax as string))catch()
        try(setUserProp bipRoot "AIRA_FitRefineFinalMaxDistance" (finalMax as string))catch()
        try(setUserProp bipRoot "AIRA_FitRefineConverged" (converged as string))catch()
        try(setUserProp bipRoot "AIRA_FitRefineTrace" trace)catch()
    ),

    fn refineBipedToGuides maxIterations =
    (
        local bipRoot = findBipedRoot()
        if bipRoot == undefined then
        (
            messageBox "No Biped root found. Create a Biped first." title:"AIRA Stage01"
            return #(false, 0, 0, 0, 0.0, 0.0, #("no_biped_root"))
        )

        if maxIterations < 0 do maxIterations = 0
        setFigureMode bipRoot true

        local pts = envelopeSamplePoints()
        local h = guideHeight()
        if h <= 1.0 do h = defaultHeight
        local initialDiag = ctVolumeDiagnostics bipRoot
        local initialFailures = initialDiag[1]
        local initialMax = initialDiag[2]
        local traceItems = #()
        append traceItems ("start ordered_root_first strictCtFailures=" + (initialFailures as string) + ", maxCtOffset=" + (initialMax as string) + ", samples=" + (initialDiag[3] as string))

        local diag = initialDiag
        local iterations = 0
        local converged = (initialFailures == 0)
        local lockedSegments = #()
        local maxSegmentIterations = maxIterations
        local initialPositions = ctCaptureBipedPositions bipRoot
        local refineMode = "ordered_root_first_candidate_ct_refinement"
        if maxSegmentIterations < 1 do maxSegmentIterations = 1

        for seg in orderedCtRefineSegments() while not converged do
        (
            log ("CT refine segment start: " + (seg[1] as string) + "->" + (seg[2] as string) + ", currentFailures=" + (diag[1] as string))
            local segmentStartPositions = ctCaptureBipedPositions bipRoot
            local segmentStartDiag = diag
            local segSearch = ctRefineSegmentCandidateSearch bipRoot seg lockedSegments pts h maxSegmentIterations false
            local beforeScore = segSearch[1]
            local afterScore = segSearch[2]
            local segmentIterations = segSearch[3]
            local acceptedMoves = segSearch[4]
            local stopReason = segSearch[5]
            iterations += segmentIterations
            local beforeDiag = #(beforeScore[1], beforeScore[5])
            local postSegmentDiag = ctVolumeDiagnosticsFromSamples bipRoot pts h
            if postSegmentDiag[1] > segmentStartDiag[1] do
            (
                ctRestoreBipedPositions bipRoot segmentStartPositions
                postSegmentDiag = segmentStartDiag
                stopReason = stopReason + "_reverted_global_regression"
            )
            local finalSegDiag = ctSegmentDiagnostics bipRoot seg pts h
            if finalSegDiag[1] == 0 do append lockedSegments seg
            append traceItems ((seg[1] as string) + "->" + (seg[2] as string) + " before=" + (beforeDiag[1] as string) + "/" + (beforeDiag[2] as string) + ", after=" + (afterScore[1] as string) + "/" + (afterScore[5] as string) + ", lockedFailures=" + (afterScore[2] as string) + ", relatedFailures=" + (afterScore[3] as string) + ", globalFailures=" + (postSegmentDiag[1] as string) + ", iter=" + (segmentIterations as string) + ", moves=" + (acceptedMoves as string) + ", stop=" + stopReason + ", locked=" + (lockedSegments.count as string))
            log ("CT refine segment done: " + (seg[1] as string) + "->" + (seg[2] as string) + ", activeFailures=" + (finalSegDiag[1] as string) + ", globalFailures=" + (postSegmentDiag[1] as string) + ", stop=" + stopReason)

            diag = postSegmentDiag
            converged = (diag[1] == 0)
        )

        if not converged do
        (
            local orderedPositions = ctCaptureBipedPositions bipRoot
            local orderedDiag = diag
            append traceItems ("ordered result not fully converged strictCtFailures " + (initialFailures as string) + " -> " + (orderedDiag[1] as string) + "; probing legacy global fallback and keeping the better result")
            ctRestoreBipedPositions bipRoot initialPositions
            local legacyResult = ctLegacyGlobalRefine bipRoot pts h maxIterations traceItems
            iterations += legacyResult[2]
            local legacyDiag = legacyResult[1]
            if ctVolumeDiagBetter legacyDiag orderedDiag then
            (
                diag = legacyDiag
                converged = legacyResult[3]
                refineMode = "ordered_root_first_candidate_ct_refinement_with_best_of_legacy_fallback"
                append traceItems ("legacy global fallback kept strictCtFailures " + (orderedDiag[1] as string) + " -> " + (legacyDiag[1] as string))
            )
            else
            (
                ctRestoreBipedPositions bipRoot orderedPositions
                diag = orderedDiag
                converged = (diag[1] == 0)
                refineMode = "ordered_root_first_candidate_ct_refinement_with_legacy_probe_kept_ordered"
                append traceItems ("legacy global fallback rejected strictCtFailures " + (legacyDiag[1] as string) + " vs ordered " + (orderedDiag[1] as string))
            )
        )

        local syncCount = syncGuidesToBiped bipRoot
        local finalFailures = diag[1]
        local finalMax = diag[2]
        local traceText = ""
        for i = 1 to traceItems.count do
        (
            traceText += traceItems[i]
            if i < traceItems.count do traceText += " | "
        )
        setFitRefineProps bipRoot refineMode maxIterations iterations initialFailures finalFailures initialMax finalMax converged traceText
        try(setUserProp bipRoot "AIRA_CTRefineGuideSyncCount" (syncCount as string))catch()
        try(setUserProp bipRoot "AIRA_CTRefineLockedSegments" (lockedSegments.count as string))catch()
        log ("Biped ordered CT refinement finished: nodeMoves=" + (iterations as string) + ", initialFailures=" + (initialFailures as string) + ", finalFailures=" + (finalFailures as string) + ", lockedSegments=" + (lockedSegments.count as string) + ", converged=" + (converged as string) + ", syncedGuides=" + (syncCount as string))
        #(converged, iterations, initialFailures, finalFailures, initialMax, finalMax, traceItems)
    ),

    fn requiredGuideNames =
    (
        #(
            "Root", "Pelvis", "Spine", "Chest", "Neck", "Head", "HeadTop",
            "CrestTop",
            "L_Clavicle", "L_Shoulder", "L_Elbow", "L_Wrist", "L_Hand", "L_HandTip",
            "L_Hip", "L_Knee", "L_Ankle", "L_Heel", "L_Foot", "L_Toe",
            "R_Clavicle", "R_Shoulder", "R_Elbow", "R_Wrist", "R_Hand", "R_HandTip",
            "R_Hip", "R_Knee", "R_Ankle", "R_Heel", "R_Foot", "R_Toe"
        )
    ),

    fn missingGuides =
    (
        local missing = #()
        for name in requiredGuideNames() where (getGuide name) == undefined do append missing name
        missing
    ),

    fn symmetryIssues =
    (
        local issues = #()
        local cx = mirrorCenterX()
        local pairs = #(
            #("L_Clavicle", "R_Clavicle"), #("L_Shoulder", "R_Shoulder"),
            #("L_Elbow", "R_Elbow"), #("L_Wrist", "R_Wrist"),
            #("L_Hand", "R_Hand"), #("L_HandTip", "R_HandTip"),
            #("L_Hip", "R_Hip"),
            #("L_Knee", "R_Knee"), #("L_Ankle", "R_Ankle"), #("L_Heel", "R_Heel"),
            #("L_Foot", "R_Foot"), #("L_Toe", "R_Toe")
        )

        for p in pairs do
        (
            local l = getGuide p[1]
            local r = getGuide p[2]
            if l != undefined and r != undefined do
            (
                local xError = abs((l.pos.x - cx) + (r.pos.x - cx))
                local yError = abs(l.pos.y - r.pos.y)
                local zError = abs(l.pos.z - r.pos.z)
                if xError > symmetryTolerance or yError > symmetryTolerance or zError > symmetryTolerance do
                (
                    append issues (p[1] + " / " + p[2] + " mismatch: x=" + (xError as string) + ", y=" + (yError as string) + ", z=" + (zError as string))
                )
            )
        )
        issues
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

    fn outputBasePath =
    (
        local base = maxFilePath
        if base == undefined or base == "" do base = getDir #export
        base
    ),

    fn writeBodyProfileReport assetName =
    (
        local base = outputBasePath()
        local jsonPath = base + "\\" + assetName + "_body_profile.json"
        local mdPath = base + "\\" + assetName + "_body_profile.md"
        local nodes = sceneModelNodes()
        local bounds = getBounds nodes
        local profile = analyzeBodyProfile nodes bounds
        local bodyType = profile[27]
        local notes = profile[28]
        local desc = "Standard or unknown character silhouette."

        if bodyType == "compact_q_bird_wide_body_short_legs" do
        (
            desc = "Compact Q-style bird hero: wide horizontal span, deep rounded body, short lower limbs, and tall head/crest area."
        )
        if bodyType == "wide_stylized_character" do
        (
            desc = "Wide stylized character: broad silhouette and non-standard body proportions."
        )

        local fp = createFile jsonPath
        format "{\n" to:fp
        format "  \"assetName\": %, \n" (jsonString assetName) to:fp
        format "  \"scene\": %, \n" (jsonString (maxFilePath + maxFileName)) to:fp
        format "  \"generatedAt\": %, \n" (jsonString (localTime as string)) to:fp
        format "  \"geometryCount\": %, \n" nodes.count to:fp
        format "  \"sampledVertexCount\": %, \n" profile[31] to:fp
        format "  \"bodyType\": %, \n" (jsonString bodyType) to:fp
        format "  \"description\": %, \n" (jsonString desc) to:fp
        format "  \"bounds\": {\n" to:fp
        format "    \"min\": %, \n" (jsonPoint profile[1]) to:fp
        format "    \"max\": %, \n" (jsonPoint profile[2]) to:fp
        format "    \"size\": %, \n" (jsonPoint profile[3]) to:fp
        format "    \"center\": %\n" (jsonPoint profile[4]) to:fp
        format "  },\n" to:fp
        format "  \"ratios\": {\n" to:fp
        format "    \"widthHeightRatio\": %, \n" (jsonNumber profile[8]) to:fp
        format "    \"depthHeightRatio\": %, \n" (jsonNumber profile[9]) to:fp
        format "    \"maxWidthZRatio\": %\n" (jsonNumber profile[30]) to:fp
        format "  },\n" to:fp
        format "  \"estimatedLandmarks\": {\n" to:fp
        format "    \"armZ\": %, \n" (jsonNumber profile[10]) to:fp
        format "    \"pelvisZ\": %, \n" (jsonNumber profile[11]) to:fp
        format "    \"hipZ\": %, \n" (jsonNumber profile[12]) to:fp
        format "    \"kneeZ\": %, \n" (jsonNumber profile[13]) to:fp
        format "    \"ankleZ\": %, \n" (jsonNumber profile[14]) to:fp
        format "    \"footZ\": %, \n" (jsonNumber profile[15]) to:fp
        format "    \"chestZ\": %, \n" (jsonNumber profile[23]) to:fp
        format "    \"neckZ\": %, \n" (jsonNumber profile[24]) to:fp
        format "    \"headZ\": %, \n" (jsonNumber profile[25]) to:fp
        format "    \"headTopZ\": %\n" (jsonNumber profile[26]) to:fp
        format "  },\n" to:fp
        format "  \"sideDepthCenters\": {\n" to:fp
        format "    \"waistY\": %, \n" (jsonNumber profile[42]) to:fp
        format "    \"torsoY\": %, \n" (jsonNumber profile[43]) to:fp
        format "    \"upperY\": %, \n" (jsonNumber profile[44]) to:fp
        format "    \"headY\": %, \n" (jsonNumber profile[45]) to:fp
        format "    \"headTopY\": %, \n" (jsonNumber profile[46]) to:fp
        format "    \"crestX\": %, \n" (jsonNumber profile[47]) to:fp
        format "    \"crestY\": %\n" (jsonNumber profile[48]) to:fp
        format "  },\n" to:fp
        format "  \"spans\": {\n" to:fp
        format "    \"maxWidth\": %, \n" (jsonNumber profile[29]) to:fp
        format "    \"shoulderHalfSpan\": %, \n" (jsonNumber profile[17]) to:fp
        format "    \"elbowHalfSpan\": %, \n" (jsonNumber profile[18]) to:fp
        format "    \"wristHalfSpan\": %, \n" (jsonNumber profile[19]) to:fp
        format "    \"footHalfSpan\": %, \n" (jsonNumber profile[20]) to:fp
        format "    \"semanticShoulderHalfSpan\": %, \n" (jsonNumber profile[32]) to:fp
        format "    \"semanticElbowHalfSpan\": %, \n" (jsonNumber profile[33]) to:fp
        format "    \"semanticWristHalfSpan\": %, \n" (jsonNumber profile[34]) to:fp
        format "    \"semanticFootHalfSpan\": %, \n" (jsonNumber profile[35]) to:fp
        format "    \"semanticMaxWidth\": %, \n" (jsonNumber profile[39]) to:fp
        format "    \"semanticMaxWidthZRatio\": %, \n" (jsonNumber profile[40]) to:fp
        format "    \"lowerRobeWidth\": %, \n" (jsonNumber (if profile.count >= 49 then profile[49] else 0.0)) to:fp
        format "    \"lowerRobeDepth\": %\n" (jsonNumber (if profile.count >= 50 then profile[50] else 0.0)) to:fp
        format "  },\n" to:fp
        format "  \"legOcclusion\": {\n" to:fp
        format "    \"occlusionLikely\": %, \n" (jsonBool (if profile.count >= 52 then profile[52] else false)) to:fp
        format "    \"mode\": %, \n" (jsonString (if (profile.count >= 52 and profile[52]) then "under_clothing_short_leg_template" else "visible_silhouette_centerline")) to:fp
        format "    \"lowerRobeCenterY\": %\n" (jsonNumber (if profile.count >= 51 then profile[51] else 0.0)) to:fp
        format "  },\n" to:fp
        format "  \"notes\": %\n" (jsonStringArray notes) to:fp
        format "}\n" to:fp
        close fp

        fp = createFile mdPath
        format "# Body Profile: %\n\n" assetName to:fp
        format "- Scene: `%`\n" (maxFilePath + maxFileName) to:fp
        format "- Generated: `%`\n" localTime to:fp
        format "- Geometry nodes: `%`\n" nodes.count to:fp
        format "- Sampled vertices: `%`\n" profile[31] to:fp
        format "- Body type: `%`\n" bodyType to:fp
        format "- Description: %\n" desc to:fp
        format "- Height: `%`\n" profile[5] to:fp
        format "- Width: `%`\n" profile[6] to:fp
        format "- Depth: `%`\n" profile[7] to:fp
        format "- Width / height ratio: `%`\n" profile[8] to:fp
        format "- Depth / height ratio: `%`\n" profile[9] to:fp
        format "- Max width Z ratio: `%`\n" profile[30] to:fp
        format "- Arm Z: `%`\n" profile[10] to:fp
        format "- Pelvis Z: `%`\n" profile[11] to:fp
        format "- Hip / knee / ankle Z: `% / % / %`\n" profile[12] profile[13] profile[14] to:fp
        format "- Shoulder / elbow / wrist half span: `% / % / %`\n" profile[17] profile[18] profile[19] to:fp
        format "- Semantic shoulder / elbow / wrist half span: `% / % / %`\n" profile[32] profile[33] profile[34] to:fp
        format "- Semantic foot half span: `%`\n" profile[35] to:fp
        format "- Semantic max width / Z ratio: `% / %`\n" profile[39] profile[40] to:fp
        format "- Lower robe width / depth: `% / %`\n" (if profile.count >= 49 then profile[49] else 0.0) (if profile.count >= 50 then profile[50] else 0.0) to:fp
        format "- Leg occlusion likely: `%`\n" (if profile.count >= 52 then profile[52] else false) to:fp
        format "- Side depth centers waist / torso / upper / head / headTop Y: `% / % / % / % / %`\n" profile[42] profile[43] profile[44] profile[45] profile[46] to:fp
        format "- Accessory crest reference X / Y: `% / %`\n" profile[47] profile[48] to:fp
        format "\n## Notes\n\n" to:fp
        for item in notes do format "- %\n" item to:fp
        close fp

        #(jsonPath, mdPath, bodyType)
    ),

    fn writeJsonPointArray fp points maxCount =
    (
        local stride = 1
        if points.count > maxCount do stride = (ceil ((points.count as float) / maxCount)) as integer
        if stride < 1 do stride = 1

        local total = 0
        for i = 1 to points.count by stride do total += 1

        format "[\n" to:fp
        local written = 0
        for i = 1 to points.count by stride do
        (
            written += 1
            format "    %" (jsonPoint points[i]) to:fp
            if written < total then format ",\n" to:fp else format "\n" to:fp
        )
        format "  ]" to:fp
        total
    ),

    fn writeVisualSnapshotReport assetName =
    (
        local base = outputBasePath()
        local jsonPath = base + "\\" + assetName + "_visual_snapshot.json"
        local nodes = sceneModelNodes()
        local bounds = getBounds nodes
        if bounds == undefined do bounds = #([ -35, -25, 0 ], [35, 25, defaultHeight])

        local pts = collectWorldMeshPoints nodes
        local names = requiredGuideNames()
        local segments = bipedSnapshotSegments()
        local bipRoot = findBipedRoot()

        local fp = createFile jsonPath
        format "{\n" to:fp
        format "  \"assetName\": %, \n" (jsonString assetName) to:fp
        format "  \"scene\": %, \n" (jsonString (maxFilePath + maxFileName)) to:fp
        format "  \"generatedAt\": %, \n" (jsonString (localTime as string)) to:fp
        format "  \"guideAlgorithm\": %, \n" (jsonString guideAlgorithm) to:fp
        format "  \"geometryCount\": %, \n" nodes.count to:fp
        format "  \"sourceVertexCount\": %, \n" pts.count to:fp
        format "  \"bounds\": {\n" to:fp
        format "    \"min\": %, \n" (jsonPoint bounds[1]) to:fp
        format "    \"max\": %, \n" (jsonPoint bounds[2]) to:fp
        format "    \"size\": %, \n" (jsonPoint (bounds[2] - bounds[1])) to:fp
        format "    \"center\": %\n" (jsonPoint ((bounds[1] + bounds[2]) / 2.0)) to:fp
        format "  },\n" to:fp

        format "  \"meshPoints\": " to:fp
        local sampledCount = writeJsonPointArray fp pts 6000
        format ",\n" to:fp
        format "  \"sampledPointCount\": %, \n" sampledCount to:fp

        format "  \"guides\": {\n" to:fp
        for i = 1 to names.count do
        (
            local g = getGuide names[i]
            format "    %: " (jsonString names[i]) to:fp
            if g == undefined then format "null" to:fp else format "%" (jsonPoint g.pos) to:fp
            if i < names.count then format ",\n" to:fp else format "\n" to:fp
        )
        format "  },\n" to:fp

        format "  \"bipedNodes\": {\n" to:fp
        local requests = fitRequests()
        for i = 1 to requests.count do
        (
            local req = requests[i]
            local node = getBipedNode bipRoot req[1] req[2]
            local nodePos = undefined
            if node != undefined do nodePos = getBipedNodePosition node
            format "    %: " (jsonString req[3]) to:fp
            if nodePos == undefined then format "null" to:fp else format "%" (jsonPoint nodePos) to:fp
            if i < requests.count then format ",\n" to:fp else format "\n" to:fp
        )
        format "  },\n" to:fp

        format "  \"bipedBones\": [\n" to:fp
        for i = 1 to segments.count do
        (
            local seg = segments[i]
            local startNode = bipedNodeForGuide bipRoot seg[1]
            local endNode = bipedNodeForGuide bipRoot seg[2]
            local startPos = if startNode != undefined then getBipedNodePosition startNode else undefined
            local endPos = if endNode != undefined then getBipedNodePosition endNode else undefined
            local startPoint = if startPos != undefined then jsonPoint startPos else "null"
            local endPoint = if endPos != undefined then jsonPoint endPos else "null"
            local boneLength = 0.0
            local boneWidth = 0.0
            local boneHeight = 0.0
            if (startPos != undefined and endPos != undefined) do
            (
                try(boneLength = distance startPos endPos)catch(boneLength = 0.0)
                local thickness = templateBoneThickness seg[1] seg[2] boneLength
                boneWidth = thickness
                boneHeight = thickness
            )
            local boneName = "Biped_" + seg[1] + "_" + seg[2]
            if (startNode != undefined and endNode != undefined) do boneName = startNode.name + "_to_" + endNode.name
            format "    {\"name\": %, \"start\": %, \"end\": %, \"role\": %, \"skinPolicy\": %, \"exists\": %, \"startNode\": %, \"endNode\": %, \"startPosition\": %, \"endPosition\": %, \"boneLength\": %, \"boneWidth\": %, \"boneHeight\": %}" \
                (jsonString boneName) (jsonString seg[1]) (jsonString seg[2]) (jsonString (templateBoneRole seg[1] seg[2])) (jsonString "biped_deforming_candidate") (jsonBool ((startNode != undefined) and (endNode != undefined))) (jsonString (if startNode != undefined then startNode.name else "")) (jsonString (if endNode != undefined then endNode.name else "")) startPoint endPoint (jsonNumber boneLength) (jsonNumber boneWidth) (jsonNumber boneHeight) to:fp
            if i < segments.count then format ",\n" to:fp else format "\n" to:fp
        )
        format "  ],\n" to:fp

        format "  \"templateBones\": [],\n" to:fp

        format "  \"bipedRoot\": %, \n" (jsonString (if bipRoot != undefined then bipRoot.name else "")) to:fp
        format "  \"visualMode\": %\n" (jsonString "local_silhouette_projection") to:fp
        format "}\n" to:fp
        close fp

        log ("Visual snapshot written: " + jsonPath)
        #(jsonPath, sampledCount)
    ),

    fn pointInsideExpandedBounds p bounds margin =
    (
        if bounds == undefined then true
        else
        (
            local mn = bounds[1] - margin
            local mx = bounds[2] + margin
            p.x >= mn.x and p.x <= mx.x and p.y >= mn.y and p.y <= mx.y and p.z >= mn.z and p.z <= mx.z
        )
    ),

    fn guideZ name =
    (
        local g = getGuide name
        if g == undefined then undefined else g.pos.z
    ),

    fn addAscendingIssue issues lowerName upperName =
    (
        local lowerZ = guideZ lowerName
        local upperZ = guideZ upperName
        if lowerZ != undefined and upperZ != undefined and upperZ <= lowerZ do
        (
            append issues (upperName + " should be above " + lowerName + ".")
        )
    ),

    fn addDescendingIssue issues upperName lowerName =
    (
        local upperZ = guideZ upperName
        local lowerZ = guideZ lowerName
        if upperZ != undefined and lowerZ != undefined and upperZ <= lowerZ do
        (
            append issues (upperName + " should be above " + lowerName + ".")
        )
    ),

    fn chainOrderIssues =
    (
        local issues = #()
        addAscendingIssue issues "Pelvis" "Spine"
        addAscendingIssue issues "Spine" "Chest"
        addAscendingIssue issues "Chest" "Neck"
        addAscendingIssue issues "Neck" "Head"
        addAscendingIssue issues "Head" "HeadTop"
        addAscendingIssue issues "HeadTop" "CrestTop"

        addDescendingIssue issues "L_Hip" "L_Knee"
        addDescendingIssue issues "L_Knee" "L_Ankle"
        addDescendingIssue issues "L_Ankle" "L_Heel"
        addDescendingIssue issues "R_Hip" "R_Knee"
        addDescendingIssue issues "R_Knee" "R_Ankle"
        addDescendingIssue issues "R_Ankle" "R_Heel"

        addDescendingIssue issues "L_Shoulder" "L_Elbow"
        addDescendingIssue issues "L_Elbow" "L_Wrist"
        addDescendingIssue issues "L_Wrist" "L_Hand"
        addDescendingIssue issues "R_Shoulder" "R_Elbow"
        addDescendingIssue issues "R_Elbow" "R_Wrist"
        addDescendingIssue issues "R_Wrist" "R_Hand"
        issues
    ),

    fn generateFitQualityReport assetName =
    (
        local base = outputBasePath()
        local jsonPath = base + "\\" + assetName + "_stage01_fit_qc.json"
        local mdPath = base + "\\" + assetName + "_stage01_fit_qc.md"
        local modelNodes = sceneModelNodes()
        local bounds = getBounds modelNodes
        local missing = missingGuides()
        local sym = symmetryIssues()
        local order = chainOrderIssues()
        local bipRoot = findBipedRoot()
        local diag = if bipRoot != undefined then fitDiagnostics bipRoot else #(#(), #(), #(), #(), 0.0, 0.0, 0, minFitTolerance, 0.0)
        local fitFailures = diag[1]
        local missingSamples = diag[3]
        local outsideSamples = diag[4]
        local totalDistance = diag[5]
        local maxDistance = diag[6]
        local sampleCount = diag[7]
        local tolerance = diag[8]
        local avgDistance = diag[9]
        local refineMode = if bipRoot != undefined then getUserPropStringSafe bipRoot "AIRA_FitRefineMode" "single_pass" else "no_biped"
        local refineMaxIterations = if bipRoot != undefined then getUserPropStringSafe bipRoot "AIRA_FitRefineMaxIterations" "0" else "0"
        local refineIterations = if bipRoot != undefined then getUserPropStringSafe bipRoot "AIRA_FitRefineIterations" "0" else "0"
        local refineInitialFailures = if bipRoot != undefined then getUserPropStringSafe bipRoot "AIRA_FitRefineInitialFailures" "0" else "0"
        local refineFinalFailures = if bipRoot != undefined then getUserPropStringSafe bipRoot "AIRA_FitRefineFinalFailures" (fitFailures.count as string) else "0"
        local refineInitialMax = if bipRoot != undefined then getUserPropStringSafe bipRoot "AIRA_FitRefineInitialMaxDistance" "0" else "0"
        local refineFinalMax = if bipRoot != undefined then getUserPropStringSafe bipRoot "AIRA_FitRefineFinalMaxDistance" (maxDistance as string) else "0"
        local refineConverged = if bipRoot != undefined then getUserPropStringSafe bipRoot "AIRA_FitRefineConverged" "false" else "false"
        local refineTrace = if bipRoot != undefined then getUserPropStringSafe bipRoot "AIRA_FitRefineTrace" "" else ""
        local mechanicalScore = 100
        if bipRoot == undefined do mechanicalScore -= 35
        mechanicalScore -= missing.count * 3
        mechanicalScore -= sym.count * 4
        mechanicalScore -= missingSamples.count * 4
        mechanicalScore -= fitFailures.count * 3
        mechanicalScore -= outsideSamples.count * 2
        mechanicalScore -= order.count * 4
        if mechanicalScore < 0 do mechanicalScore = 0

        local guideSource = "tutorial_centerline_qbird_visual_candidate"
        local decisionPolicy = "visual_semantic_gate_only"
        local scorePolicy = "scores_disabled_for_decision_diagnostic_only"
        local productionReady = (mechanicalScore >= 85 and missing.count == 0 and sym.count == 0 and fitFailures.count == 0 and order.count == 0 and false)
        local semanticConfidence = "low"
        local semanticWarning = "Guides were generated as a visual candidate. Numeric fit diagnostics can pass while anatomical landmarks are still wrong; manual or vision-based landmark review is required."

        local fp = createFile jsonPath
        format "{\n" to:fp
        format "  \"assetName\": %, \n" (jsonString assetName) to:fp
        format "  \"scene\": %, \n" (jsonString (maxFilePath + maxFileName)) to:fp
        format "  \"generatedAt\": %, \n" (jsonString (localTime as string)) to:fp
        format "  \"modelGeometryCount\": %, \n" modelNodes.count to:fp
        format "  \"bipedFound\": %, \n" (jsonBool (bipRoot != undefined)) to:fp
        format "  \"bipedRoot\": %, \n" (jsonString (if bipRoot != undefined then bipRoot.name else "")) to:fp
        format "  \"guideSource\": %, \n" (jsonString guideSource) to:fp
        format "  \"decisionPolicy\": %, \n" (jsonString decisionPolicy) to:fp
        format "  \"scorePolicy\": %, \n" (jsonString scorePolicy) to:fp
        format "  \"semanticConfidence\": %, \n" (jsonString semanticConfidence) to:fp
        format "  \"productionReady\": %, \n" (jsonBool productionReady) to:fp
        format "  \"mechanicalScore\": %, \n" mechanicalScore to:fp
        format "  \"fitTolerance\": %, \n" (jsonNumber tolerance) to:fp
        format "  \"fitSamples\": %, \n" sampleCount to:fp
        format "  \"averageGuideNodeDistance\": %, \n" (jsonNumber avgDistance) to:fp
        format "  \"maxGuideNodeDistance\": %, \n" (jsonNumber maxDistance) to:fp
        format "  \"fitRefinement\": {\n" to:fp
        format "    \"mode\": %, \n" (jsonString refineMode) to:fp
        format "    \"maxIterations\": %, \n" refineMaxIterations to:fp
        format "    \"iterations\": %, \n" refineIterations to:fp
        format "    \"initialFailures\": %, \n" refineInitialFailures to:fp
        format "    \"finalFailures\": %, \n" refineFinalFailures to:fp
        format "    \"initialMaxDistance\": %, \n" refineInitialMax to:fp
        format "    \"finalMaxDistance\": %, \n" refineFinalMax to:fp
        format "    \"converged\": %, \n" (jsonBool (refineConverged == "true" or refineConverged == "True")) to:fp
        format "    \"trace\": %\n" (jsonString refineTrace) to:fp
        format "  },\n" to:fp
        format "  \"missingGuides\": %, \n" (jsonStringArray missing) to:fp
        format "  \"symmetryIssues\": %, \n" (jsonStringArray sym) to:fp
        format "  \"missingFitSamples\": %, \n" (jsonStringArray missingSamples) to:fp
        format "  \"fitFailures\": %, \n" (jsonStringArray fitFailures) to:fp
        format "  \"outsideBoundsSamples\": %, \n" (jsonStringArray outsideSamples) to:fp
        format "  \"chainOrderIssues\": %, \n" (jsonStringArray order) to:fp
        format "  \"semanticWarning\": %\n" (jsonString semanticWarning) to:fp
        format "}\n" to:fp
        close fp

        fp = createFile mdPath
        format "# Stage01 Fit QC: %\n\n" assetName to:fp
        format "- Scene: `%`\n" (maxFilePath + maxFileName) to:fp
        format "- Generated: `%`\n" localTime to:fp
        format "- Model geometry nodes: `%`\n" modelNodes.count to:fp
        format "- Biped found: `%`\n" (bipRoot != undefined) to:fp
        if bipRoot != undefined do format "- Biped root: `%`\n" bipRoot.name to:fp
        format "- Decision policy: `%`\n" decisionPolicy to:fp
        format "- Score policy: `%`\n" scorePolicy to:fp
        format "- Legacy mechanical rating field: `hidden_diagnostic_only`\n" to:fp
        format "- Production ready: `%`\n" productionReady to:fp
        format "- Guide source: `%`\n" guideSource to:fp
        format "- Semantic confidence: `%`\n" semanticConfidence to:fp
        format "- Fit tolerance: `%`\n" tolerance to:fp
        format "- Fit samples: `%`\n" sampleCount to:fp
        format "- Average guide-node distance: `%`\n" avgDistance to:fp
        format "- Max guide-node distance: `%`\n" maxDistance to:fp
        format "- Fit refinement mode: `%`\n" refineMode to:fp
        format "- Fit refinement iterations: `% / %`\n" refineIterations refineMaxIterations to:fp
        format "- Fit refinement failures: `% -> %`\n" refineInitialFailures refineFinalFailures to:fp
        format "- Fit refinement converged: `%`\n" refineConverged to:fp
        if refineTrace != "" do format "- Fit refinement trace: `%`\n" refineTrace to:fp
        format "\n## Mechanical Issues\n\n" to:fp
        if missing.count + sym.count + missingSamples.count + fitFailures.count + outsideSamples.count + order.count == 0 then
        (
            format "- None\n" to:fp
        )
        else
        (
            for item in missing do format "- Missing guide: %\n" item to:fp
            for item in sym do format "- Symmetry: %\n" item to:fp
            for item in missingSamples do format "- Missing fit sample: %\n" item to:fp
            for item in fitFailures do format "- Fit failure: %\n" item to:fp
            for item in outsideSamples do format "- Bounds: %\n" item to:fp
            for item in order do format "- Chain order: %\n" item to:fp
        )
        format "\n## Semantic Gate\n\n" to:fp
        format "- %\n" semanticWarning to:fp
        format "- This report proves Biped nodes match current guides; it does not prove the guides are correct anatomical landmarks.\n" to:fp
        close fp

        #(jsonPath, mdPath, mechanicalScore, productionReady)
    ),

    fn generateTemplateSkeletonQualityReport assetName =
    (
        log "Template skeleton QC is disabled. Stage01 validates the fitted Biped only."
        #("", "", 0, false, false)
    ),

    fn reportPath =
    (
        local base = maxFilePath
        if base == undefined or base == "" do base = getDir #export
        base + "\\AIRA_stage01_biped_report.md"
    ),

    fn writeArrayItems fp items prefixText =
    (
        if items.count == 0 then
        (
            format "%None\n" prefixText to:fp
        )
        else
        (
            for item in items do format "%%\n" prefixText item to:fp
        )
    ),

    fn generateReport =
    (
        local path = reportPath()
        local fp = createFile path
        local nodes = selectedModelNodes()
        local bounds = getBounds nodes
        local missing = missingGuides()
        local sym = symmetryIssues()
        local bipRoot = findBipedRoot()

        format "# AIRA Stage 01 Biped Report\n\n" to:fp
        format "- Scene: `%`\n" (maxFilePath + maxFileName) to:fp
        format "- Generated: `%`\n" localTime to:fp
        format "- Selected model nodes: `%`\n" nodes.count to:fp
        if bounds != undefined do
        (
            format "- Bounds min: `%`\n" bounds[1] to:fp
            format "- Bounds max: `%`\n" bounds[2] to:fp
            format "- Bounds size: `%`\n" (bounds[2] - bounds[1]) to:fp
        )
        format "- Guide prefix: `%`\n" guidePrefix to:fp
        format "- Biped found: `%`\n" (bipRoot != undefined) to:fp
        if bipRoot != undefined do format "- Biped root: `%`\n" bipRoot.name to:fp

        format "\n## Missing Guides\n\n" to:fp
        writeArrayItems fp missing "- "

        format "\n## Symmetry Issues\n\n" to:fp
        writeArrayItems fp sym "- "

        format "\n## Stage 01 Checklist\n\n" to:fp
        format "- [ ] Model pivot / transform reviewed\n" to:fp
        format "- [ ] Main body guides placed on visible joints\n" to:fp
        format "- [ ] Left and right guide symmetry reviewed\n" to:fp
        format "- [ ] Biped created with the expected structure\n" to:fp
        format "- [ ] Biped fitted in Figure Mode\n" to:fp
        format "- [ ] Hands, fingers, feet and head manually inspected\n" to:fp
        format "- [ ] File saved as a rig work version\n" to:fp

        close fp
        log ("Report written: " + path)
        path
    ),

    fn validateStage01 =
    (
        local missing = missingGuides()
        local sym = symmetryIssues()
        local bipRoot = findBipedRoot()
        local msg = "Stage01 validation\n\n"

        msg += ("Missing guides: " + (missing.count as string) + "\n")
        msg += ("Symmetry issues: " + (sym.count as string) + "\n")
        msg += ("Biped found: " + ((bipRoot != undefined) as string) + "\n\n")
        msg += "A Markdown report will be generated next."
        messageBox msg title:"AIRA Stage01"
        generateReport()
    ),

    fn saveRigVersion =
    (
        local base = maxFilePath
        if base == undefined or base == "" then
        (
            messageBox "Save the scene once before using version save." title:"AIRA Stage01"
            undefined
        )
        else
        (
            local cleanName = if maxFileName == "" then "untitled.max" else maxFileName
            local nameNoExt = getFilenameFile cleanName
            local path = base + nameNoExt + "_stage01_biped.max"
            saveMaxFile path
            log ("Saved rig version: " + path)
            path
        )
    )
)

AIRA_Stage01 = AIRAStage01Tool()

if AIRA_STAGE01_HEADLESS != true do
(
    try(destroyDialog AIRA_Stage01_UI)catch()

    rollout AIRA_Stage01_UI "AIRA Stage01 Biped" width:310 height:365
    (
        label lblTitle "Guide-based Biped setup for 3ds Max 2020+" align:#left
        label lblFlow "Select model -> create guides -> adjust -> create biped" align:#left

        groupBox grpGuides "Guides" pos:[10,50] width:290 height:105
        button btnCreateGuides "Create / Update Guides" pos:[25,75] width:260 height:25
        button btnMirror "Mirror L Guides To R" pos:[25,107] width:260 height:25

        groupBox grpBiped "Biped" pos:[10,165] width:290 height:105
        button btnCreateBiped "Create Biped From Guides" pos:[25,190] width:260 height:25
        button btnFitBiped "Fit Existing Biped To Guides" pos:[25,222] width:260 height:25

        groupBox grpReport "Check / Save" pos:[10,280] width:290 height:72
        button btnValidate "Validate / Report" pos:[25,305] width:125 height:25
        button btnSave "Save Stage01 File" pos:[160,305] width:125 height:25

        on btnCreateGuides pressed do
        (
            AIRA_Stage01.createGuidesFromSelection()
        )

        on btnMirror pressed do
        (
            AIRA_Stage01.mirrorLeftGuidesToRight()
        )

        on btnCreateBiped pressed do
        (
            AIRA_Stage01.createBipedFromGuides()
        )

        on btnFitBiped pressed do
        (
            local bipRoot = AIRA_Stage01.findBipedRoot()
            AIRA_Stage01.fitBipedToGuides bipRoot
        )

        on btnValidate pressed do
        (
            AIRA_Stage01.validateStage01()
        )

        on btnSave pressed do
        (
            AIRA_Stage01.saveRigVersion()
        )
    )

    createDialog AIRA_Stage01_UI
    AIRA_Stage01.log "Loaded. Use the AIRA Stage01 Biped window."
)

if AIRA_STAGE01_HEADLESS == true do
(
    AIRA_Stage01.log "Loaded in headless mode."
)
