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
global AIRA_AssetQC

struct AIRAMCPBridge
(
    host = "127.0.0.1",
    port = 37820,
    listener = undefined,
    stage01Path = @"F:\workspace\github\3dsmax-ai-rig-assistant\maxscript\aira_stage01_biped.ms",
    assetQcPath = @"F:\workspace\github\3dsmax-ai-rig-assistant\maxscript\aira_asset_qc.ms",

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

rollout AIRA_MCP_Bridge_UI "AIRA MCP Bridge" width:280 height:86
(
    label lblStatus "Bridge not started." pos:[12,12] width:255 height:18
    label lblPort "127.0.0.1:37820" pos:[12,34] width:255 height:18
    timer tmrBridge interval:100 active:true

    on AIRA_MCP_Bridge_UI open do
    (
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
