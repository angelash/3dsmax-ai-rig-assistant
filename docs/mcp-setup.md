# 3ds Max AI Rig Assistant：MCP 接入与运行

> 当前生产口径：旧算法 benchmark、qualityScore 排序、默认推荐检查和推荐提升都已屏蔽。MCP/批处理只允许 `tutorial_centerline_qbird` 作为视觉候选生成器；Skin 放行必须依赖截图、Semantic Skin Review 和人工/VLM 语义确认。

这套 MCP 接入由两部分组成：

1. 3ds Max 内部桥接脚本：`maxscript/aira_mcp_bridge.ms`
2. Python MCP server：`server/mcp_server.py`

MCP server 不直接执行任意 MaxScript，只能调用桥接脚本暴露的白名单命令。

## 1. 安装 Python 依赖

建议使用工具目录里的隔离虚拟环境，避免影响全局 Python：

```powershell
python -m venv F:\workspace\github\3dsmax-ai-rig-assistant\.venv
F:\workspace\github\3dsmax-ai-rig-assistant\.venv\Scripts\python.exe -m pip install -r F:\workspace\github\3dsmax-ai-rig-assistant\requirements.txt
```

## 2. 在 3ds Max 内启动桥接脚本

打开 3ds Max 2020，运行：

```text
Scripting > Run Script...
```

选择：

```text
F:\workspace\github\3dsmax-ai-rig-assistant\maxscript\aira_mcp_bridge.ms
```

成功后会看到一个小窗口：

```text
AIRA MCP Bridge
Bridge running.
127.0.0.1:37820
```

## 3. 先用直连 CLI 测试

在 PowerShell 里执行：

```powershell
F:\workspace\github\3dsmax-ai-rig-assistant\.venv\Scripts\python.exe F:\workspace\github\3dsmax-ai-rig-assistant\server\direct_cli.py ping
```

如果返回 `ok: true`，说明 Python 已经能和 3ds Max 通信。

## 4. 运行第一篇全自动粗流程

先在 3ds Max 里选中角色模型，然后执行：

```powershell
F:\workspace\github\3dsmax-ai-rig-assistant\.venv\Scripts\python.exe F:\workspace\github\3dsmax-ai-rig-assistant\server\direct_cli.py stage01_auto_pipeline
```

也可以直接运行封装好的脚本：

```powershell
F:\workspace\github\3dsmax-ai-rig-assistant\server\stage01_auto.ps1
```

它会自动执行：

1. 加载 Stage01 工具。
2. 根据当前选中模型生成 Guide。
3. 镜像左侧 Guide 到右侧。
4. 创建 Biped。
5. 生成 Stage01 Markdown 报告。

注意：这是“粗自动化”。Guide 初始位置来自模型包围盒，不等于美术级精确关节点。真实项目里仍建议人工检查骨盆、膝盖、脚踝、肩肘腕、头颈和手指。

## 5. 运行资产质检

检测当前 3ds Max 场景：

```powershell
F:\workspace\github\3dsmax-ai-rig-assistant\.venv\Scripts\python.exe F:\workspace\github\3dsmax-ai-rig-assistant\server\direct_cli.py asset_qc_current_scene
```

离线检测一个 FBX：

```powershell
F:\workspace\github\3dsmax-ai-rig-assistant\server\batch_qc_fbx.ps1 -SourceFbx "F:\workspace\github\3dsmax-ai-rig-assistant\source\luxun_model\陆逊模型.fbx" -AssetName luxun_model
```

输出目录：

```text
F:/workspace/github/3dsmax-ai-rig-assistant/out/
```

报告包括几何、三角面、材质贴图、包围盒、缩放、骨骼、Skin、权重影响数和问题列表。

## 6. 接入 MCP 客户端

示例配置：

```json
{
  "mcpServers": {
    "3dsmax-ai-rig-assistant": {
      "command": "F:\\workspace\\github\\3dsmax-ai-rig-assistant\\.venv\\Scripts\\python.exe",
      "args": [
        "F:\\workspace\\github\\3dsmax-ai-rig-assistant\\server\\mcp_server.py"
      ],
      "env": {}
    }
  }
}
```

同样的配置已放在：

```text
F:/workspace/github/3dsmax-ai-rig-assistant/config/mcp.example.json
```

如果使用 Cursor，可以参考 `.cursor/mcp.json`。

手动启动 MCP server 时也可以执行：

```powershell
F:\workspace\github\3dsmax-ai-rig-assistant\server\run_mcp_server.ps1
```

## 7. 当前 MCP 工具

| MCP 工具 | 作用 |
| --- | --- |
| `ping_3dsmax` | 检查 Max 桥接是否在线 |
| `stage01_load_tool` | 在 Max 中加载 Stage01 工具 |
| `stage01_create_guides` | 从当前选择生成 Guide |
| `stage01_mirror_guides` | 镜像左侧 Guide 到右侧 |
| `stage01_create_biped` | 按 Guide 创建 Biped |
| `stage01_fit_biped` | 将已有 Biped 重新贴合 Guide |
| `stage01_generate_report` | 生成 Markdown 报告 |
| `stage01_generate_fit_qc` | 生成当前场景 Biped 贴合质量报告 |
| `stage01_save_file` | 另存 Stage01 工作文件 |
| `stage01_auto_pipeline` | 一键粗流程 |
| `asset_qc_current_scene` | 对当前 Max 场景生成资产质检报告 |
| `asset_qc_fbx_file` | 用 `3dsmaxbatch.exe` 离线检测本地 FBX |
| `stage01_rig_fbx_file` | 用 `3dsmaxbatch.exe` 离线生成 Stage01 视觉候选、证据包、可选 VLM 签核和 Skin gate，只允许 `tutorial_centerline_qbird` |

旧的多算法 benchmark、`qualityScore` 排序和 `default_recommended/` 提升流程已经禁用。相关历史文件只作为回溯材料，不再作为默认入口。

离线 Stage01 流程也会生成本地视觉轮廓 QC：

```text
*_visual_qc.md
*_visual_snapshot.json
visual_screenshots/<asset>/*_front.png
visual_screenshots/<asset>/*_side.png
visual_screenshots/<asset>/*_top.png
```

这一步是本地投影和规则自检，不是外部视觉大模型。截图可继续喂给人工或 VLM 做语义复核。脚本里的旧分数字段只作为兼容诊断数据，不参与 Skin 放行。

离线流程还会生成 `visual_review/` 证据包：全局前/侧/顶图、head/pelvis/hand/foot 局部裁剪、`review_input.md` 和 `review_schema.json`。这个包用于人工或 VLM 输出结构化 blocker，不产生质量分。有 `OPENAI_API_KEY` 时，batch 会自动调用 VLM 生成 `*_semantic_visual_review_vlm.json`；传 `skip_vlm_review=true` 或 PowerShell 的 `-SkipVlmReview` 可强制跳过，传 `visual_signoff_json` / `-VisualSignoffJson` 可使用外部签核。

旧 benchmark 曾写入：

```text
F:/workspace/github/3dsmax-ai-rig-assistant/out/algorithm_benchmarks/<RunId>/run_manifest.json
```

旧 benchmark 归档如需研究性回看，必须显式声明这是历史评分，不允许用于生产判断：

```powershell
F:\workspace\github\3dsmax-ai-rig-assistant\server\list_algorithm_benchmarks.ps1 -LegacyScoringResearchOnly
```

几何骨架探测：

```powershell
F:\workspace\github\3dsmax-ai-rig-assistant\server\export_fbx_obj.ps1 -SourceFbx "F:\workspace\github\3dsmax-ai-rig-assistant\source\luxun_model\陆逊模型.fbx" -AssetName luxun_model_external
F:\workspace\github\3dsmax-ai-rig-assistant\.venv\Scripts\python.exe F:\workspace\github\3dsmax-ai-rig-assistant\server\skeletor_probe.py F:\workspace\github\3dsmax-ai-rig-assistant\out\luxun_model_external.obj --asset-name luxun_model_external
```

## 8. 安全边界

当前桥接只接受固定字符串命令，不接受任意 MaxScript 文本。这是有意设计：AI 可以调工具，但不能随便改场景。
