# 3ds Max AI Rig Assistant：Stage02 Skin 设置与初始权重

Stage02 对应教程第三、四篇：

- `video-tutorials/BV1ftReBYEg3-03-skin-setup-and-prop-weights.md`
- `video-tutorials/BV1ftReBYEg3-04-body-weights-and-final-check.md`

这一阶段是独立执行入口，只读取已经存在的 Stage01 Biped 场景，不创建 Guide，不重新拟合 Biped，也不修改 Stage01 绑骨逻辑。

## 已实现能力

脚本位置：

`F:/workspace/github/3dsmax-ai-rig-assistant/maxscript/aira_stage02_skin.ms`

功能：

| 功能 | 说明 |
| --- | --- |
| Add Skin Modifier | 给候选模型节点添加 `Skin/蒙皮` 修改器，已有 Skin 时复用 |
| Add Biped Bones | 只把变形用 Biped 节点加入 Skin，Biped COM 保持 control-only |
| Bone Affect Limit | 默认按教程设置为 `3`，并兼容项目 QC 的 `<= 4` 限制 |
| Initial Weight Pass | 根据 Biped 段、左右侧、身高区域做第一轮顶点权重 |
| Remove Zero Weights | 可用时调用 Skin 的清理 0 权重操作 |
| Stage02 Report | 输出 JSON/Markdown，明确标记还需人工变形测试和权重细刷 |

## 执行方式

推荐从 Stage01 产出的 `.max` 场景继续：

```powershell
F:\workspace\github\3dsmax-ai-rig-assistant\server\batch_stage02_skin.ps1 `
  -SourceMax "F:\workspace\github\3dsmax-ai-rig-assistant\out\runs\luxun_model__YYYYMMDD_HHMMSS\scene\luxun_model_stage01_rig_scene.max" `
  -AssetName luxun_model `
  -Stage01SkinPrepGateJson "F:\workspace\github\3dsmax-ai-rig-assistant\out\runs\luxun_model__YYYYMMDD_HHMMSS\data\luxun_model_stage01_skin_prep_gate.json"
```

默认要求 `Stage01SkinPrepGateJson.skinSetupReady=true`。如果只是研究第一版自动权重，可以显式加：

```powershell
-AllowBlockedStage01
```

加这个开关时仍会执行 Skin 初始搭建，但报告会把结果标记为 research-only，`productionReady=false`。

## 输出

每次运行会写入：

```text
out/stage02_runs/<assetName>__YYYYMMDD_HHMMSS/
  scene/
    <assetName>_stage02_skin_scene.max
  reports/
    <assetName>_stage02_batch_summary.md
    <assetName>_stage02_skin_report.md
  data/
    <assetName>_stage02_skin_report.json
    <assetName>_stage02_skin_asset_qc.json
    <assetName>_stage02_skin_asset_qc.md
  logs/
    <assetName>_stage02_3dsmaxbatch.log
    <assetName>_stage02_listener.log
```

## 当前边界

- 第一版权重是初始权重，不是商用品质最终权重。
- 道具/附件如果没有独立语义骨骼映射，会先按最近 Biped 段获得初始影响；炮、枪、背包、耳机等刚性道具仍需要后续专门规则或人工刷成 `1`。
- 身体、头颈、肩、腕、腿、脚需要按教程第四篇做临时动作测试和人工细刷。
- `skinWeightsComplete=false`、`deformationTestComplete=false`、`productionReady=false` 会保持到人工/动画测试完成。

## 规则继承

Stage02 继承当前 Stage01 的生产口径：

- 只使用 Biped 作为身体 Skin 主骨架。
- `AIRA_Biped_COM` / vertical root 是控制轴，不作为身体变形骨骼加入 Skin。
- `AIRA_BONE_*` 模板骨不参与当前身体 Skin 流程。
- 没有通过 Stage01 多视图包裹性和语义确认时，Stage02 只能作为研究输出，不能进入生产交付。
