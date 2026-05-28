# Stage01 Output Layout

这份文档定义 Stage01 单次运行产物的交付结构。目标是让后续 MDC 复查、参考答案比对、自动学习校对和 Stage02 Skin 接入都能快速定位上下文。

## 需求分析

当前产物的问题不是数量不足，而是阅读顺序不够明确：`scene/`、`data/`、`reports/`、`visual_review/` 等目录按文件类型分组，适合脚本查找，但不适合人按“这一步做了什么、下一步看什么”来接手。

新版布局补充三件事：

- 目录加编号，表达推荐操作和复查顺序。
- 根 README 说明每一步做了什么、产出物是什么、如何解读、有什么作用。
- 每个编号目录也有自己的 README，避免只靠文件名猜含义。

额外补充：

- 保留 `layout_manifest.json`，记录旧目录到新编号目录的映射。
- 明确区分 `Guide`、候选 `Biped`、参考答案骨架、最终 Skin 结果。
- JSON 和 Markdown 内部的相对路径会重写到新编号目录，减少断链。
- 编号表达复查/交接顺序；真实生成时间仍以 batch summary 和 logs 为准。

## 编号目录

| Step | Directory | Meaning |
| --- | --- | --- |
| 01 | `01_scene_workspace/` | 工作 FBX、贴图 sidecar、Stage01 候选 Biped `.max` 场景 |
| 02 | `02_generation_logs/` | 3ds Max batch/listener 原始日志 |
| 03 | `03_stage01_data/` | body profile、visual snapshot、fit QC、gate 等 JSON |
| 04 | `04_stage01_reports/` | MDC 可读 Markdown 报告 |
| 05 | `05_qc_silhouette_views/` | visual_qc 根据 snapshot 画出的三视图 |
| 06 | `06_textured_model_views/` | 3ds Max 带贴图视图 |
| 07 | `07_wire_bone_technical_views/` | 3ds Max 线框 + Guide + 候选 Biped 技术视图 |
| 08 | `08_visual_review_evidence/` | 全局图、局部裁剪、语义叠加、切片和审查模板 |
| 09 | `09_view_indexes/` | front/side/top 按视角组织的导航索引 |

## 使用入口

跑完 `server/batch_stage01_fbx.ps1` 后，脚本会在最后调用：

```powershell
.venv\Scripts\python.exe server\stage01_numbered_layout.py --run-dir <runDir> --asset-name <assetName>
```

这个步骤只在 Stage01 所有 QC、视觉证据包、Skin gate 都完成后执行，避免中间脚本仍按旧目录读写时被打断。

## 解读原则

- 先读 run 根目录 `README.md`。
- 判断候选骨架位置时，优先看 `07_wire_bone_technical_views/`。
- 看角色语义上下文时，对照 `06_textured_model_views/`。
- 看局部证据和 blocker 时，进入 `08_visual_review_evidence/`；其中 `slices/` 是 CT-style 逐关节切片，红框或红叉表示骨心未被局部点云截面严格包裹。
- 需要继续编辑时，打开 `01_scene_workspace/*.max`。

## 横向报告

全量复查报告由 `server/build_stage01_audit_report.py` 从 `out/runs` 生成到 `report/<pack>/`。报告按“同一种图横向看所有模型”组织，每个图组目录只保留：

- `contact_sheet.png`：把该阶段/视角的所有模型拼成一张大图，红框表示当前 run 仍有机械或 CT blocker。
- `index.html`：浏览器入口，显示大图和行列索引。
- `index.md`：纯文本索引，记录大图中每个模型所在行列、run README 和关键 flags。

## 实验输出

临时探针、抽样重跑、参数对比等实验性输出必须放在 `out/experiments/<experiment_name>/` 下，不要在工程根目录创建 `out_ct_probe*`、`out_test*` 这类平级目录。`out/` 整体已忽略，根目录误建的新实验目录应该在 `git status` 中暴露出来并迁回 `out/experiments/`。

## 限制

这个布局不等于生产交付。图里的 Biped 仍是由 Guide 初始化并经 CT 切片保守修正后的候选骨架，不是参考答案骨架，也不是完成 Skin 权重后的生产交付。
