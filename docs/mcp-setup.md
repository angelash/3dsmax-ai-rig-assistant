# 3ds Max AI Rig Assistant：MCP 接入与运行

> 当前生产口径：旧算法 benchmark、qualityScore 排序、默认推荐检查和推荐提升都已屏蔽。MCP/批处理只允许 `tutorial_centerline_qbird` 作为视觉候选生成器；Skin 放行必须依赖截图、Semantic Skin Review 和 MDC 本地代理语义确认。

这套 MCP 接入由两部分组成：

1. 3ds Max 内部桥接脚本：`maxscript/aira_mcp_bridge.ms`
2. Python MCP server：`server/mcp_server.py`

MCP server 不直接执行任意 MaxScript，只能调用桥接脚本暴露的白名单命令。

## 1. 本机自配置

每台电脑首次同步仓库后，先在仓库根目录运行：

```powershell
.\server\setup_local.ps1
```

它会创建/使用 `.venv`、安装基础依赖、探测 `3dsmaxbatch.exe`，并生成不提交的本机配置：

- `config/local.json`
- `config/mcp.local.json`

只生成配置、不安装依赖：

```powershell
.\server\setup_local.ps1 -SkipVenv -SkipInstall
```

配置读取优先级是：命令行参数 > `AIRA_*` 环境变量 > `config/local.json` > 自动推导默认值。

## 2. 在 3ds Max 内启动桥接脚本

打开 3ds Max 2020，运行：

```text
Scripting > Run Script...
```

选择：

```text
<repo>\maxscript\aira_mcp_bridge.ms
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
.\server\doctor.ps1 -CheckBridge
```

如果 `checks` 里的 `3dsmax_bridge` 为 `ok`，说明 Python 已经能和 3ds Max 通信；如果是 `warning`，通常是 3ds Max 里的桥接脚本还没启动。

## 4. 运行第一篇全自动粗流程

先在 3ds Max 里选中角色模型，然后执行：

```powershell
.\server\stage01_auto.ps1
```

也可以直接调直连 CLI：

```powershell
.\.venv\Scripts\python.exe .\server\direct_cli.py stage01_auto_pipeline
```

它会自动执行：

1. 加载 Stage01 工具。
2. 根据当前选中模型生成 Guide。
3. 镜像左侧 Guide 到右侧。
4. 创建 Biped。
5. 生成 Stage01 Markdown 报告。

注意：这是“粗自动化”。Guide 初始位置来自模型包围盒，不等于美术级精确关节点。真实项目里仍需要 MDC 本地代理检查骨盆、膝盖、脚踝、肩肘腕、头颈和手指。

## 5. 运行资产质检

检测当前 3ds Max 场景：

```powershell
.\.venv\Scripts\python.exe .\server\direct_cli.py asset_qc_current_scene
```

离线检测一个 FBX：

```powershell
$repo = (Resolve-Path .).Path
& "$repo\server\batch_qc_fbx.ps1" -SourceFbx "$repo\source\luxun_model\陆逊模型.fbx" -AssetName luxun_model
```

输出目录：

```text
out/
```

报告包括几何、三角面、材质贴图、包围盒、缩放、骨骼、Skin、权重影响数和问题列表。

## 6. 接入 MCP 客户端

优先使用自配置生成的本机配置：

```text
config/mcp.local.json
```

通用模板在 `config/mcp.example.json`，里面的 `C:\path\to\...` 需要替换成本机路径。`mcp.local.json` 已经包含本机 `AIRA_TOOL_ROOT`、`AIRA_OUT_DIR`、`AIRA_SOURCE_ROOT`、`AIRA_MAXBATCH`、`AIRA_MCP_HOST` 和 `AIRA_MCP_PORT`。

手动启动 MCP server 时也可以执行：

```powershell
.\server\run_mcp_server.ps1
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
| `stage01_rig_fbx_file` | 用 `3dsmaxbatch.exe` 离线生成 Stage01 视觉候选、证据包和 Skin gate，只允许 `tutorial_centerline_qbird` |
| `stage02_load_tool` | 在 Max 中加载独立 Stage02 Skin 工具 |
| `stage02_skin_current_scene` | 对当前 Max 场景执行 Stage02 初始 Skin 设置，未提供 gate 时仅为研究输出 |
| `stage02_skin_max_file` | 用 `3dsmaxbatch.exe` 从 Stage01 `.max` 场景独立执行 Skin 设置和第一版权重，可选用参考 FBX 权重压缩，默认要求 Skin gate 通过 |

旧的多算法 benchmark、`qualityScore` 排序和 `default_recommended/` 提升流程已经禁用。相关历史文件只作为回溯材料，不再作为默认入口。

离线 Stage01 流程也会生成本地视觉轮廓 QC：

```text
*_visual_qc.md
*_visual_snapshot.json
visual_screenshots/<asset>/*_front.png
visual_screenshots/<asset>/*_side.png
visual_screenshots/<asset>/*_top.png
```

这一步是本地投影和规则自检，不是外部视觉大模型。截图继续交给 MDC 本地代理做语义复核。脚本里的旧分数字段只作为兼容诊断数据，不参与 Skin 放行。

离线流程还会生成 `visual_review/` 证据包：全局前/侧/顶图、head/pelvis/hand/foot 局部裁剪、`review_input.md` 和 `review_schema.json`。这个包用于 MDC 本地代理输出结构化 blocker，不产生质量分。批处理不会调用外部视觉 API；传 `visual_signoff_json` / `-VisualSignoffJson` 可使用已完成的本地签核。

Biped 机械拟合不是单次写入。离线流程会按 Fit QC 偏差循环调整：先根据 Guide 段长缩放 Biped，再按教程层级顺序重新定位，直到无 fit failure 或达到 `max_fit_iterations` / `-MaxFitIterations` 上限。未收敛时 Skin gate 会继续阻断。

旧 benchmark 曾写入：

```text
out/algorithm_benchmarks/<RunId>/run_manifest.json
```

旧 benchmark 归档如需研究性回看，必须显式声明这是历史评分，不允许用于生产判断：

```powershell
.\server\list_algorithm_benchmarks.ps1 -LegacyScoringResearchOnly
```

几何骨架探测：

```powershell
$repo = (Resolve-Path .).Path
& "$repo\server\export_fbx_obj.ps1" -SourceFbx "$repo\source\luxun_model\陆逊模型.fbx" -AssetName luxun_model_external
& "$repo\.venv\Scripts\python.exe" "$repo\server\skeletor_probe.py" "$repo\out\luxun_model_external.obj" --asset-name luxun_model_external
```

## 8. 安全边界

当前桥接只接受固定字符串命令，不接受任意 MaxScript 文本。这是有意设计：AI 可以调工具，但不能随便改场景。
