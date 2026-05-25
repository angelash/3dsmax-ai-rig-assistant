/*
AI Rig Assistant - 3ds Max MCP Bridge
Target: 3ds Max 2020+ / MAXScript

Run this script inside 3ds Max before using the MCP server.
It opens a localhost TCP bridge on 127.0.0.1:37820 and exposes a small
whitelisted command set to the Python MCP server.

Commands are line-delimited plain text. Responses are one-line JSON.
*/

global AIRA_MCP_Bridge
global AIRA_MCP_Bridge_UI
global AIRA_Stage01
global AIRA_Stage02
global AIRA_AssetQC

fn AIRA_bridgeGetEnv key defaultValue =
(
    local value = (dotNetClass "System.Environment").GetEnvironmentVariable key
    if value == undefined or value == "" then defaultValue else value
)

fn AIRA_bridgeJoinPath dir fileName =
(
    local d = dir as string
    if d == "" then fileName
    else
    (
        local lastChar = substring d d.count 1
        if lastChar == "\\" or lastChar == "/" then d + fileName else d + "\\" + fileName
    )
)

fn AIRA_bridgeParentDir path =
(
    local di = dotNetObject "System.IO.DirectoryInfo" path
    di.Parent.FullName
)

fn AIRA_bridgeScriptRoot =
(
    local sourceFile = ""
    try(sourceFile = getSourceFileName())catch(sourceFile = "")
    if sourceFile != undefined and sourceFile != "" then getFilenamePath sourceFile else ""
)

fn AIRA_bridgeToolRoot =
(
    local envRoot = AIRA_bridgeGetEnv "AIRA_TOOL_ROOT" ""
    if envRoot != "" then envRoot
    else
    (
        local scriptRoot = AIRA_bridgeScriptRoot()
        if scriptRoot != "" then AIRA_bridgeParentDir scriptRoot else "."
    )
)

struct AIRAMCPBridge
(
    host = AIRA_bridgeGetEnv "AIRA_MCP_HOST" "127.0.0.1",
    port = (AIRA_bridgeGetEnv "AIRA_MCP_PORT" "37820") as integer,
    listener = undefined,
    toolRoot = AIRA_bridgeToolRoot(),
    stage01Path = "",
    stage02Path = "",
    assetQcPath = "",

    fn log msg =
    (
        format "[AIRA MCP Bridge] %\n" msg
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

    fn jsonResponse ok action message result =
    (
        "{\"ok\":" + (if ok then "true" else "false") + \
        ",\"action\":\"" + jsonEscape action + "\"" + \
        ",\"message\":\"" + jsonEscape message + "\"" + \
        ",\"result\":\"" + jsonEscape result + "\"" + \
        "}"
    ),

    fn applyConfig =
    (
        host = AIRA_bridgeGetEnv "AIRA_MCP_HOST" host
        port = (AIRA_bridgeGetEnv "AIRA_MCP_PORT" (port as string)) as integer
        toolRoot = AIRA_bridgeToolRoot()
        local maxscriptDir = AIRA_bridgeJoinPath toolRoot "maxscript"
        stage01Path = AIRA_bridgeJoinPath maxscriptDir "aira_stage01_biped.ms"
        stage02Path = AIRA_bridgeJoinPath maxscriptDir "aira_stage02_skin.ms"
        assetQcPath = AIRA_bridgeJoinPath maxscriptDir "aira_asset_qc.ms"
        true
    ),

    fn ensureStage01Loaded =
    (
        if AIRA_Stage01 == undefined do
        (
            if doesFileExist stage01Path then
            (
                fileIn stage01Path
            )
            else
            (
                log ("Stage01 script missing: " + stage01Path)
            )
        )
        AIRA_Stage01 != undefined
    ),

    fn ensureAssetQcLoaded =
    (
        if AIRA_AssetQC == undefined do
        (
            if doesFileExist assetQcPath then
            (
                fileIn assetQcPath
            )
            else
            (
                log ("Asset QC script missing: " + assetQcPath)
            )
        )
        AIRA_AssetQC != undefined
    ),

    fn ensureStage02Loaded =
    (
        if AIRA_Stage02 == undefined do
        (
            if doesFileExist stage02Path then
            (
                fileIn stage02Path
            )
            else
            (
                log ("Stage02 script missing: " + stage02Path)
            )
        )
        AIRA_Stage02 != undefined
    ),

    fn startListener =
    (
        if listener != undefined do
        (
            try(listener.Stop())catch()
            listener = undefined
        )

        local ip = (dotNetClass "System.Net.IPAddress").Parse host
        listener = dotNetObject "System.Net.Sockets.TcpListener" ip port
        listener.Start()
        log ("Listening on " + host + ":" + (port as string))
        true
    ),

    fn stopListener =
    (
        if listener != undefined do
        (
            try(listener.Stop())catch()
            listener = undefined
        )
        log "Stopped."
        true
    ),

    fn dispatch action =
    (
        case action of
        (
            "ping":
            (
                jsonResponse true action "3ds Max bridge is alive." (maxFilePath + maxFileName)
            )

            "stage01_load_tool":
            (
                if ensureStage01Loaded() then
                    jsonResponse true action "Stage01 tool loaded." stage01Path
                else
                    jsonResponse false action "Could not load Stage01 tool." stage01Path
            )

            "stage01_create_guides":
            (
                if ensureStage01Loaded() then
                (
                    local count = AIRA_Stage01.createGuidesFromSelection()
                    jsonResponse true action ("Created / updated " + (count as string) + " guides.") (count as string)
                )
                else jsonResponse false action "Stage01 tool is not loaded." ""
            )

            "stage01_mirror_guides":
            (
                if ensureStage01Loaded() then
                (
                    local count = AIRA_Stage01.mirrorLeftGuidesToRight()
                    jsonResponse true action ("Mirrored " + (count as string) + " guide pairs.") (count as string)
                )
                else jsonResponse false action "Stage01 tool is not loaded." ""
            )

            "stage01_create_biped":
            (
                if ensureStage01Loaded() then
                (
                    local bip = AIRA_Stage01.createBipedFromGuides()
                    if bip != undefined then
                        jsonResponse true action "Created Biped from guides." bip.name
                    else
                        jsonResponse false action "Biped creation returned undefined." ""
                )
                else jsonResponse false action "Stage01 tool is not loaded." ""
            )

            "stage01_fit_biped":
            (
                if ensureStage01Loaded() then
                (
                    local bipRoot = AIRA_Stage01.findBipedRoot()
                    local ok = AIRA_Stage01.fitBipedToGuides bipRoot
                    jsonResponse ok action "Fit existing Biped to guides." ""
                )
                else jsonResponse false action "Stage01 tool is not loaded." ""
            )

            "stage01_generate_report":
            (
                if ensureStage01Loaded() then
                (
                    local path = AIRA_Stage01.generateReport()
                    jsonResponse true action "Generated Stage01 report." path
                )
                else jsonResponse false action "Stage01 tool is not loaded." ""
            )

            "stage01_generate_fit_qc":
            (
                if ensureStage01Loaded() then
                (
                    local result = AIRA_Stage01.generateFitQualityReport "current_scene"
                    jsonResponse true action ("Generated Stage01 fit QC. Legacy scores are diagnostic-only; productionReady=" + (result[4] as string)) (result[1] + "|" + result[2])
                )
                else jsonResponse false action "Stage01 tool is not loaded." ""
            )

            "stage01_save_file":
            (
                if ensureStage01Loaded() then
                (
                    local path = AIRA_Stage01.saveRigVersion()
                    if path != undefined then
                        jsonResponse true action "Saved Stage01 file." path
                    else
                        jsonResponse false action "Could not save Stage01 file. Save the scene once first." ""
                )
                else jsonResponse false action "Stage01 tool is not loaded." ""
            )

            "stage01_auto_pipeline":
            (
                if ensureStage01Loaded() then
                (
                    local guideCount = AIRA_Stage01.createGuidesFromSelection()
                    local mirrorCount = AIRA_Stage01.mirrorLeftGuidesToRight()
                    local bip = AIRA_Stage01.createBipedFromGuides()
                    local report = AIRA_Stage01.generateReport()
                    local bipName = if bip != undefined then bip.name else ""
                    jsonResponse true action ("Auto pipeline finished. Guides=" + (guideCount as string) + ", mirrored=" + (mirrorCount as string) + ", biped=" + bipName) report
                )
                else jsonResponse false action "Stage01 tool is not loaded." ""
            )

            "asset_qc_current_scene":
            (
                if ensureAssetQcLoaded() then
                (
                    local result = AIRA_AssetQC.writeReports "current_scene"
                    jsonResponse true action ("Asset QC report generated. Issues=" + (result[3] as string)) (result[1] + "|" + result[2])
                )
                else jsonResponse false action "Asset QC tool is not loaded." ""
            )

            "stage02_load_tool":
            (
                if ensureStage02Loaded() then
                    jsonResponse true action "Stage02 Skin tool loaded." stage02Path
                else
                    jsonResponse false action "Could not load Stage02 Skin tool." stage02Path
            )

            "stage02_skin_current_scene":
            (
                if ensureStage02Loaded() then
                (
                    local result = AIRA_Stage02.runInitialSkin "current_scene"
                    jsonResponse true action ("Stage02 Skin setup generated. skinSetupReady=" + (result[3] as string) + ", issues=" + (result[4] as string)) (result[1] + "|" + result[2])
                )
                else jsonResponse false action "Stage02 Skin tool is not loaded." ""
            )

            default:
            (
                jsonResponse false action "Unknown command." ""
            )
        )
    ),

    fn handleClient client =
    (
        local response = jsonResponse false "unknown" "Unhandled bridge error." ""
        try
        (
            local stream = client.GetStream()
            local reader = dotNetObject "System.IO.StreamReader" stream
            local writer = dotNetObject "System.IO.StreamWriter" stream
            writer.AutoFlush = true
            local action = reader.ReadLine()
            if action == undefined do action = ""
            action = action as string
            response = dispatch action
            writer.WriteLine response
            try(reader.Close())catch()
            try(writer.Close())catch()
        )
        catch ex
        (
            response = jsonResponse false "exception" (ex as string) ""
        )
        try(client.Close())catch()
        response
    ),

    fn poll =
    (
        if listener != undefined do
        (
            try
            (
                while listener.Pending() do
                (
                    local client = listener.AcceptTcpClient()
                    handleClient client
                )
            )
            catch ex
            (
                log ("Poll error: " + (ex as string))
            )
        )
    )
)

try(destroyDialog AIRA_MCP_Bridge_UI)catch()
try(if AIRA_MCP_Bridge != undefined do AIRA_MCP_Bridge.stopListener())catch()

AIRA_MCP_Bridge = AIRAMCPBridge()
AIRA_MCP_Bridge.applyConfig()

rollout AIRA_MCP_Bridge_UI "AIRA MCP Bridge" width:280 height:86
(
    label lblStatus "Bridge not started." pos:[12,12] width:255 height:18
    label lblPort "" pos:[12,34] width:255 height:18
    timer tmrBridge interval:100 active:true

    on AIRA_MCP_Bridge_UI open do
    (
        AIRA_MCP_Bridge.applyConfig()
        lblPort.text = AIRA_MCP_Bridge.host + ":" + (AIRA_MCP_Bridge.port as string)
        local ok = AIRA_MCP_Bridge.startListener()
        lblStatus.text = if ok then "Bridge running." else "Bridge failed."
    )

    on tmrBridge tick do
    (
        AIRA_MCP_Bridge.poll()
    )

    on AIRA_MCP_Bridge_UI close do
    (
        AIRA_MCP_Bridge.stopListener()
    )
)

createDialog AIRA_MCP_Bridge_UI
