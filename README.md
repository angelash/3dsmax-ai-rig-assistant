# 3ds Max AI Rig Assistant

这是一个面向 3ds Max 2020+ 的 AI 辅助绑定/资产质检工具原型。当前版本包含两条生产入口：

- Stage 01：Biped 骨架 Guide 创建与粗匹配。
- Asset QC：读取 FBX/当前场景，输出游戏资产质检 JSON + Markdown 报告。

核心思路：

```text
AI / 人工指令
  -> 安全工具函数
  -> MaxScript
  -> 3ds Max Biped / Guide / 报告
```

MCP 入口只暴露白名单工具，不让 AI 任意执行 MaxScript。

## 当前文件

| 路径 | 说明 |
| --- | --- |
| `maxscript/aira_stage01_biped.ms` | 3ds Max 里直接运行的 Stage01 工具 |
| `maxscript/aira_asset_qc.ms` | 资产质检工具，输出 JSON/Markdown |
| `maxscript/aira_mcp_bridge.ms` | 3ds Max 内部 MCP/TCP 桥接脚本 |
| `maxscript/batch_asset_qc_fbx.ms` | `3dsmaxbatch.exe` 离线检测 FBX 的 MaxScript |
| `server/mcp_server.py` | Python MCP server，暴露白名单工具 |
| `server/direct_cli.py` | 不经过 MCP 客户端的直连测试命令 |
| `server/run_mcp_server.ps1` | 手动启动 MCP server |
| `server/stage01_auto.ps1` | 直连执行 Stage01 粗自动流程 |
| `server/batch_qc_fbx.ps1` | 离线检测任意本地 FBX |
| `server/batch_qc_luxun.ps1` | 陆逊模型的离线检测样例 |
| `server/benchmark_luxun_algorithms.ps1` | 旧算法评分入口，生产默认禁用 |
| `server/check_algorithm_default.ps1` | 旧推荐检查入口，生产默认禁用 |
| `server/list_algorithm_benchmarks.ps1` | 旧 benchmark 历史汇总，默认禁用 |
| `server/promote_recommended_algorithm.ps1` | 旧推荐提升入口，生产默认禁用 |
| `server/visual_qc.py` | 从三维快照生成前/侧/顶视觉轮廓图和本地视觉 QC |
| `server/visual_review_pack.py` | 从视觉快照、QC 和 Skin gate 生成视觉语义证据包、局部裁剪和审查 schema |
| `server/vlm_multiview_review.py` | 调用视觉大模型读取多视图证据包并输出结构化 Stage01 签核 JSON |
| `server/rig_detail_review.py` | 按教程顺序逐骨检查位置、长度、方向、粗细和镜像 |
| `server/stage01_skin_prep_gate.py` | 汇总 Stage01 QC，生成进入 Skin 前的人工/VLM 语义确认和权重准备门 |
| `server/organize_out_dir.py` | 整理 `out/`，把同一批次的场景、报告、数据、日志和截图归入 `runs/<assetName>__YYYYMMDD_HHMMSS/scene|reports|data|logs|screenshots|views/` 并生成说明文档 |
| `presets/luban_stage01_biped.json` | 鲁班七号这类卡通矮角色的 Biped 结构预设 |
| `presets/guide_algorithms.json` | Guide 候选生成器登记表，当前只启用 `tutorial_centerline_qbird` |
| `docs/stage01-workflow.md` | 使用流程、坐标约定、边界说明 |
| `docs/bone-fit-qc-method.md` | 骨骼适配自检指标和改进路线 |
| `docs/auto-rigging-algorithm-survey.md` | 自动绑定算法调研和接入评估 |
| `docs/mcp-setup.md` | MCP 接入与运行说明 |
| `docs/mcp-tool-contract.md` | 后续 MCP 白名单工具契约草案 |
| `docs/video-tutorials/` | 鲁班七号 3ds Max 绑定教程整理稿、截图和逐字稿 |

本地实验模型和贴图放在 `source/`，例如 `source/luxun_model/陆逊模型.fbx` 和同名 `.fbm/` 贴图目录。`source/` 已加入 `.gitignore`，只作为本机运行输入，不提交到仓库。

## 快速使用

1. 在 3ds Max 2020+ 打开角色模型。
2. 选择角色模型。
3. 运行：

   ```text
   Scripting > Run Script > F:/workspace/github/3dsmax-ai-rig-assistant/maxscript/aira_stage01_biped.ms
   ```

4. 点击 `Create / Update Guides`。
5. 手动把 `AIRA_GUIDE_*` 定位点拖到关节位置。
6. 点击 `Create Biped From Guides`。
7. 人工检查 Figure Mode 下的 Biped 匹配。
8. 点击 `Validate / Report` 生成阶段报告。

## 资产质检

离线检测一个 FBX：

```powershell
F:\workspace\github\3dsmax-ai-rig-assistant\server\batch_qc_fbx.ps1 -SourceFbx "F:\workspace\github\3dsmax-ai-rig-assistant\source\luxun_model\陆逊模型.fbx" -AssetName luxun_model
```

输出在 `F:/workspace/github/3dsmax-ai-rig-assistant/out/`：

- `luxun_model_asset_qc.json`
- `luxun_model_asset_qc.md`
- `luxun_model_raw_asset_qc_scene.max`

当前检测项包括：几何数量、三角面数、顶点数、材质/贴图路径、包围盒尺寸、是否居中、缩放、骨骼节点、Skin Modifier、骨骼影响数、无权重点和问题列表。

## 骨骼适配自检

离线生成 Stage01 骨架和自检报告：

```powershell
F:\workspace\github\3dsmax-ai-rig-assistant\server\batch_stage01_fbx.ps1 -SourceFbx "F:\workspace\github\3dsmax-ai-rig-assistant\source\luxun_model\陆逊模型.fbx" -AssetName luxun_model
```

默认也是唯一允许的 Guide 候选生成器是 `tutorial_centerline_qbird`。旧的 `bbox_humanoid`、`mesh_profile`、`qbird_profile`、`semantic_qbird`、`visual_semantic_qbird`、`tutorial_visual_qbird` 已屏蔽，不能再作为推荐或生产判断入口。

batch 会在创建 Biped 后进入证据反馈循环：每轮读取当前 Biped 节点到 Guide 的偏差，先用 Figure Mode scale 调整 Biped 段长，再按教程层级顺序重新定位；默认最多 `-MaxFitIterations 12` 轮，收敛后才生成最终 Fit QC。机械收敛仍不是 Skin 放行，front/side/top 视觉签核仍是硬门。对宽袍、裙摆、披风或靴筒遮挡腿部的角色，流程会标记 `legClothingOcclusion`，Guide 生成会把 Hip/Knee/Ankle 放到更保守的隐藏腿轴线上，不能让腿链追衣服外轮廓。

关键输出会在 batch 结束后自动整理到 `out/runs/<assetName>__YYYYMMDD_HHMMSS/`。同一个 `assetName` 反复生成时会新建带时间戳的 run 目录，不覆盖旧批次。主要文件包括：

- `luxun_model_stage01_rig_scene.max`：包含按教程原则创建和视觉校准后的 Biped 骨架。
- `luxun_model_body_profile.json`：体型识别和比例量化报告。
- `luxun_model_stage01_fit_qc.json`：Biped 贴合自检。
- `luxun_model_visual_qc.json`：本地视觉轮廓自检。
- `visual_review/`：视觉语义审查证据包，包含全局证据图、头/手/脚/骨盆裁剪图、`review_input.md` 和结构化审查 schema。
- `visual_review/*_semantic_visual_review_vlm.json`：如果设置了 `OPENAI_API_KEY` 且未传 `-SkipVlmReview`，batch 会自动生成 VLM 多视图签核结果。
- `luxun_model_rig_detail_review.json`：按教程顺序的逐骨检查。
- `luxun_model_stage01_skin_prep_gate.json`：Stage01 到 Skin 的交付门，列出人工/VLM 语义确认、Skin/权重阻塞项和下一步任务。
- `visual_screenshots/luxun_model/`：前视图、侧视图、顶视图 PNG。
- `luxun_model_stage01_rig_asset_qc.json`：生成骨骼后的资产质检。

Stage01 会先从 mesh 顶点做高度切片，识别宽高比、深高比、最大横向展开高度、短腿比例和下半身衣服遮挡风险，再生成一套视觉候选 Guide。当前只保留 `tutorial_centerline_qbird` 作为候选生成器：它按 `BV1ftReBYEg3-01-biped-skeleton-and-matching` 的教程顺序先定身体/腿/躯干；腿被袍摆或靴筒遮挡时，Hip/Knee/Ankle 采用隐藏腿轴线而不是衣服边；手、肩、肘、腕放到局部肢体截面的修剪中心线，而不是贴到点云外表面。它不是“评分推荐算法”，只负责模拟人工看前/侧/顶视图校准 Biped 关节点；场景和 Skin 准备流程只使用 Biped，不生成普通 Bones 模板骨链。详见 `docs/bone-fit-qc-method.md`。

`rig_detail_review.py` 除了逐骨诊断，还会输出 Semantic Skin Review：例如 Biped COM 是否只能作为控制轴、HeadTop 是否可能被冠/头饰极值拉偏、单块手部是否需要 Biped 手指/细节结构、脚掌/Toe 是否必须用 side/top 视图签核。`stage01_skin_prep_gate.py` 会把 Biped 贴合输出、视觉截图、逐骨诊断、Semantic Skin Review、front/side/top 包裹性签核和资产 QC 合并成 Skin 前置报告。当前 `tutorial_centerline_qbird` 只能形成 Stage01 视觉候选；没有人工签核或 VLM 输出全部通过 `visual_review/review_schema.json` 前，`semanticSkinReady=false`、`stage01HandoffReady=false`、`productionReady=false`。

视觉自检当前是本地 2D 轮廓投影，不是外部视觉大模型：MaxScript 导出 mesh 点云、Guide 和 Biped 节点/骨段，`visual_qc.py` 生成前/侧/顶 PNG，并检查视觉轮廓比例、Guide 顺序、对称性、离轮廓距离、手部中心线覆盖和手臂截面中心线覆盖。截图里的红色/紫色十字是视觉目标点，连线是 guide 到目标的偏差。

`visual_review_pack.py` 会在 run 内生成 `visual_review/`：`full/` 保存全局前/侧/顶证据图，`regions/` 保存 head、pelvis、left/right hand、left/right foot 的局部裁剪，`review_input.md` 和 `review_schema.json` 用于人工或 VLM 做结构化语义审查。它只输出 blocker/pass/uncertain 这类审查项，不输出分数。硬规则是：frontWrap、sideWrap、topWrap、rootPelvisPolicy、legClothingOcclusion、footPivot 等必要检查没有全部 `pass`，不得进入 Skin。规则细节见 `docs/stage01-biped-multiview-signoff.md`。

`batch_stage01_fbx.ps1` 会在证据包生成后执行最终 Skin gate：如果传入 `-VisualSignoffJson`，使用该签核；如果设置了 `OPENAI_API_KEY` 且未传 `-SkipVlmReview`，调用 `vlm_multiview_review.py` 自动生成 VLM 签核；如果没有签核，gate 会保持阻断并说明缺少多视图包裹性确认。VLM 只提供语义签核 JSON，不直接放行；最终仍由 `stage01_skin_prep_gate.py` 校验 schema、必填检查项、Biped fit 和资产 QC。

整理已有输出目录：

```powershell
F:\workspace\github\3dsmax-ai-rig-assistant\.venv\Scripts\python.exe F:\workspace\github\3dsmax-ai-rig-assistant\server\organize_out_dir.py --out-dir F:\workspace\github\3dsmax-ai-rig-assistant\out
```

`batch_stage01_fbx.ps1` 会在每次生成结束后自动调用这个整理脚本；这个命令主要用于整理历史输出或手动刷新 README。整理后每个 `out/runs/<assetName>__YYYYMMDD_HHMMSS/README.md` 会说明该模型大致由哪个命令、哪个视觉候选生成器生成，并汇总当前语义阻塞项。run 根目录不再平铺文件，而是按用途放到：

- `scene/`：`.max` 场景和工作 `.fbx`。
- `screenshots/`：front / side / top PNG。
- `reports/`：给人看的 Markdown 报告。
- `data/`：给脚本和复查用的 JSON / snapshot。
- `logs/`：3ds Max batch/listener 日志。
- `visual_review/`：视觉语义证据包和结构化审查模板。
- `views/`：`front.md`、`side.md`、`top.md` 这类按截图视角组织的索引，只引用文件，不复制重复产物。

跨 run 的截图索引写入 `out/_indexes/screenshot_output_pairs.md/json`。

## 旧算法评分已停用

旧的多算法 benchmark、qualityScore 排序、默认推荐检查和推荐提升都已经从生产链路中屏蔽。相关脚本默认会直接报错，只有显式加研究用参数时才允许查看历史归档。

当前生产判断只看：

- `tutorial_centerline_qbird` 生成的视觉候选骨架。
- front / side / top 截图和视角索引。
- Semantic Skin Review 中的语义阻塞项。
- 人工或 VLM 对 front / side / top 包裹性的结构化签核。
- 人工/VLM 语义确认、Skin、权重和变形测试。

旧 JSON 里的 `mechanicalScore`、`visualScore`、`detailScore`、`qualityScore` 等字段只保留为兼容诊断数据，不再展示为推荐依据，也不能让 `productionReady` 变成 true。

几何骨架外部探测需要额外依赖：

```powershell
F:\workspace\github\3dsmax-ai-rig-assistant\.venv\Scripts\python.exe -m pip install -r F:\workspace\github\3dsmax-ai-rig-assistant\requirements-geometry.txt
```

## MCP 运行

1. 在 3ds Max 中运行 `maxscript/aira_mcp_bridge.ms`。
2. 用隔离环境运行 MCP server，配置见 `config/mcp.example.json`。
3. 先用直连命令检查：

   ```powershell
   F:\workspace\github\3dsmax-ai-rig-assistant\.venv\Scripts\python.exe F:\workspace\github\3dsmax-ai-rig-assistant\server\direct_cli.py ping
   ```

4. 需要检测当前 Max 场景时：

   ```powershell
   F:\workspace\github\3dsmax-ai-rig-assistant\.venv\Scripts\python.exe F:\workspace\github\3dsmax-ai-rig-assistant\server\direct_cli.py asset_qc_current_scene
   ```

5. 需要粗自动执行第一篇流程时：

   ```powershell
   F:\workspace\github\3dsmax-ai-rig-assistant\.venv\Scripts\python.exe F:\workspace\github\3dsmax-ai-rig-assistant\server\direct_cli.py stage01_auto_pipeline
   ```

## 为什么先用 Guide

第一篇教程里最难自动化的不是创建 Biped，而是“视觉对齐”：骨盆、膝盖、脚踝、手腕、手指、脖子和头都需要贴合模型形体。直接让 AI 猜这些点不稳定。Guide 流程把问题拆开：

- 脚本生成统一命名的定位点。
- 人或后续视觉算法负责把定位点放准。
- 脚本按定位点创建和贴合 Biped。

这个方案更稳，也更适合后续接 MCP。

## 下一步

1. 增加 A1/小程序角色资源规格配置，例如三角面、贴图尺寸、骨骼数量、命名规则。
2. 增加自动修复工具：贴图路径本地化、材质重命名、Root/缩放规范化。
3. 根据项目角色朝向和单位修正 `facingAngle`、Guide 初始比例。
4. 给手指、翅膀、武器 Socket 增加更细的 Guide 匹配。
