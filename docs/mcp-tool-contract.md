# 3ds Max AI Rig Assistant：MCP 工具契约

这一版已经接入本地 MCP/TCP 桥接。这里记录当前和后续 MCP 服务应该暴露的安全工具函数，避免让 AI 任意执行 MaxScript。

## 设计原则

- MCP 只调用白名单工具函数。
- 每个工具函数都应该可回滚或只做低风险修改。
- 修改场景前先生成摘要，必要时让用户确认。
- 每次执行后返回结构化结果：成功状态、修改对象、警告、报告路径。

## Stage01 工具

### AnalyzeScene

输入：

```json
{}
```

输出：

```json
{
  "ok": true,
  "selected_nodes": 1,
  "bounds": {
    "min": [0, 0, 0],
    "max": [100, 50, 160]
  },
  "biped_found": false,
  "guide_count": 0,
  "warnings": []
}
```

### CreateGuidesFromSelection

输入：

```json
{
  "preset": "luban_stage01_biped"
}
```

输出：

```json
{
  "ok": true,
  "created_or_updated": 27,
  "guide_prefix": "AIRA_GUIDE_",
  "warnings": []
}
```

### MirrorLeftGuidesToRight

输入：

```json
{
  "mirror_axis": "X",
  "center_x": 0
}
```

输出：

```json
{
  "ok": true,
  "mirrored_pairs": 10,
  "warnings": []
}
```

### CreateBipedFromGuides

输入：

```json
{
  "preset": "luban_stage01_biped",
  "fit_after_create": true
}
```

输出：

```json
{
  "ok": true,
  "biped_root": "AIRA_Biped_COM",
  "fit_nodes": 23,
  "warnings": [
    "Manual inspection is still required for hands, fingers and feet."
  ]
}
```

### ValidateStage01

输入：

```json
{}
```

输出：

```json
{
  "ok": true,
  "missing_guides": [],
  "symmetry_issues": [],
  "biped_found": true,
  "report_path": "AIRA_stage01_biped_report.md"
}
```

### GenerateStage01FitQC

输入：

```json
{}
```

输出：

```json
{
  "ok": true,
  "message": "Generated Stage01 fit QC. Legacy scores are diagnostic-only; productionReady=false",
  "result": "stage01_fit_qc.json|stage01_fit_qc.md"
}
```

## Asset QC 工具

### AssetQCCurrentScene

输入：

```json
{}
```

输出：

```json
{
  "ok": true,
  "message": "Asset QC report generated. Issues=3",
  "result": "asset_qc.json|asset_qc.md"
}
```

### AssetQCFbxFile

输入：

```json
{
  "fbx_path": "F:\\workspace\\open-share\\陆逊模型.fbx",
  "asset_name": "luxun_model"
}
```

### Stage01RigFbxFile

输入：

```json
{
  "fbx_path": "F:\\workspace\\open-share\\陆逊模型.fbx",
  "asset_name": "luxun_model",
  "guide_algorithm": "tutorial_centerline_qbird"
}
```

`guide_algorithm` 只允许 `tutorial_centerline_qbird`。旧算法和分数排序推荐已经屏蔽，不能再通过 MCP 作为生产入口。

输出：

```json
{
  "ok": true,
  "runDir": "F:/workspace/github/3dsmax-ai-rig-assistant/out/runs/luxun_model__YYYYMMDD_HHMMSS",
  "guideAlgorithm": "tutorial_centerline_qbird",
  "workingFbx": "F:/workspace/github/3dsmax-ai-rig-assistant/out/runs/luxun_model__YYYYMMDD_HHMMSS/scene/luxun_model.fbx",
  "textureSidecar": "F:/workspace/github/3dsmax-ai-rig-assistant/out/runs/luxun_model__YYYYMMDD_HHMMSS/scene/luxun_model.fbm",
  "scene": "F:/workspace/github/3dsmax-ai-rig-assistant/out/runs/luxun_model__YYYYMMDD_HHMMSS/scene/luxun_model_stage01_rig_scene.max",
  "summary": "F:/workspace/github/3dsmax-ai-rig-assistant/out/runs/luxun_model__YYYYMMDD_HHMMSS/reports/luxun_model_stage01_batch_summary.md",
  "fitQcJson": "F:/workspace/github/3dsmax-ai-rig-assistant/out/runs/luxun_model__YYYYMMDD_HHMMSS/data/luxun_model_stage01_fit_qc.json",
  "templateSkeletonQcJson": "F:/workspace/github/3dsmax-ai-rig-assistant/out/runs/luxun_model__YYYYMMDD_HHMMSS/data/luxun_model_template_skeleton_fit_qc.json",
  "rigDetailReviewJson": "F:/workspace/github/3dsmax-ai-rig-assistant/out/runs/luxun_model__YYYYMMDD_HHMMSS/data/luxun_model_rig_detail_review.json",
  "visualReviewManifest": "F:/workspace/github/3dsmax-ai-rig-assistant/out/runs/luxun_model__YYYYMMDD_HHMMSS/visual_review/luxun_model_visual_evidence_manifest.json",
  "visualReviewInput": "F:/workspace/github/3dsmax-ai-rig-assistant/out/runs/luxun_model__YYYYMMDD_HHMMSS/visual_review/review_input.md",
  "visualReviewSchema": "F:/workspace/github/3dsmax-ai-rig-assistant/out/runs/luxun_model__YYYYMMDD_HHMMSS/visual_review/review_schema.json",
  "wireBoneScreenshotDir": "F:/workspace/github/3dsmax-ai-rig-assistant/out/runs/luxun_model__YYYYMMDD_HHMMSS/wire_bone_screenshots",
  "stage01SkinPrepGateJson": "F:/workspace/github/3dsmax-ai-rig-assistant/out/runs/luxun_model__YYYYMMDD_HHMMSS/data/luxun_model_stage01_skin_prep_gate.json",
  "rigAssetQcJson": "F:/workspace/github/3dsmax-ai-rig-assistant/out/runs/luxun_model__YYYYMMDD_HHMMSS/data/luxun_model_stage01_rig_asset_qc.json"
}
```

`stage01SkinPrepGateJson` 汇总模板输出、视觉截图、逐骨诊断、Semantic Skin Review 和资产 QC。它用于说明为什么 Stage01 结果只是视觉候选，还不能进入生产交付：语义阻塞项、人工语义确认、Skin Modifier、权重和变形检查未完成时，`stage01HandoffReady=false`、`skinSetupReady=false`、`productionReady=false`。

`textureSidecar` 指向与工作 FBX/Max 场景同目录保存的 `.fbm` 贴图目录。批处理会把源 FBX 旁边的 `.fbm` 复制进 run，并在 3ds Max 导入后按文件名把 bitmap 贴图改为相对路径，避免旧机器上的绝对路径继续污染 Asset QC。

`visualReviewManifest` / `visualReviewInput` / `visualReviewSchema` 指向 run 内的视觉语义证据包。它包含全局证据图、头/手/脚/骨盆局部裁剪和结构化 blocker 审查 schema，不输出质量分。

`wireBoneScreenshotDir` 指向 3ds Max 技术视图截图目录。这里的 front / side / top PNG 使用线框材质叠加模板骨骼和 guide，用来直观看侧面重心、腰部原点、头/帽分离和骨骼粗细。

输出：

```json
{
  "ok": true,
  "assetName": "luxun_model",
  "json": "F:/workspace/github/3dsmax-ai-rig-assistant/out/luxun_model_asset_qc.json",
  "markdown": "F:/workspace/github/3dsmax-ai-rig-assistant/out/luxun_model_asset_qc.md",
  "scene": "F:/workspace/github/3dsmax-ai-rig-assistant/out/luxun_model_asset_qc_scene.max"
}
```

当前 Asset QC 检测项：

- 几何数量、三角面数、顶点数。
- 包围盒、宽高比、是否居中、底部是否贴近 0。
- 材质名、贴图数量、丢失贴图、绝对路径贴图。
- 骨骼类节点数量、Skin Modifier、骨骼引用数。
- 单顶点最大骨骼影响数、无权重点。
- 问题列表，用于 AI 解释和后续修复建议。

## 后续阶段

第二阶段可以继续加：

```text
CreatePropBoneGuides()
CreateAccessoryBones()
LinkAccessoryBonesToBiped()
ValidateAccessoryRig()
```

第三、四阶段再加：

```text
AddSkinModifier()
AddSkinBones()
AssignRigidPropWeights()
ValidateSkinInfluenceLimit()
GenerateSkinReport()
```
