# 3ds Max AI Rig Assistant：Stage02 Skin 设置与初始权重

Stage02 对应教程第三、四篇：

- `video-tutorials/BV1ftReBYEg3-03-skin-setup-and-prop-weights.md`
- `video-tutorials/BV1ftReBYEg3-04-body-weights-and-final-check.md`

这一阶段是独立执行入口，只读取已经存在的 Stage01 Biped 场景，不创建 Guide，不重新拟合 Biped，也不修改 Stage01 绑骨逻辑。

## 已实现能力

脚本位置：

`maxscript/aira_stage02_skin.ms`

功能：

| 功能 | 说明 |
| --- | --- |
| Add Skin Modifier | 给候选模型节点添加 `Skin/蒙皮` 修改器，已有 Skin 时复用 |
| Add Biped Bones | 只把变形用 Biped 节点加入 Skin，Biped COM 保持 control-only |
| Bone Affect Limit | 默认按教程设置为 `3`，并兼容项目 QC 的 `<= 4` 限制 |
| Initial Weight Pass | 根据 Biped 段、左右侧、身高区域做第一轮顶点权重 |
| Reference Weight Collapse | 可选读取已蒙皮参考 FBX，把参考 Skin 权重按语义压缩到当前简化 Biped 变形骨 |
| Remove Zero Weights | 可用时调用 Skin 的清理 0 权重操作 |
| Deformation Smoke Test | 从 Stage02 场景自动摆基础测试 pose，输出三视图截图、位移统计和 posed scene |
| Stage02 Report | 输出 JSON/Markdown，明确标记还需人工变形测试和权重细刷 |

## 执行方式

推荐从 Stage01 产出的 `.max` 场景继续：

```powershell
$repo = (Resolve-Path .).Path
& "$repo\server\batch_stage02_skin.ps1" `
  -SourceMax "$repo\out\runs\luxun_model__YYYYMMDD_HHMMSS\scene\luxun_model_stage01_rig_scene.max" `
  -AssetName luxun_model `
  -Stage01SkinPrepGateJson "$repo\out\runs\luxun_model__YYYYMMDD_HHMMSS\data\luxun_model_stage01_skin_prep_gate.json"
```

默认要求 `Stage01SkinPrepGateJson.skinSetupReady=true`。如果只是研究第一版自动权重，可以显式加：

```powershell
-AllowBlockedStage01
```

加这个开关时仍会执行 Skin 初始搭建，但报告会把结果标记为 research-only，`productionReady=false`。

如果同一拓扑有参考答案 FBX，可以把参考 Skin 权重作为初始蒙皮来源：

```powershell
$repo = (Resolve-Path .).Path
& "$repo\server\batch_stage02_skin.ps1" `
  -SourceMax "$repo\out\runs\luxun_model__YYYYMMDD_HHMMSS\scene\luxun_model_stage01_rig_scene.max" `
  -AssetName luxun_model `
  -Stage01SkinPrepGateJson "$repo\out\runs\luxun_model__YYYYMMDD_HHMMSS\data\luxun_model_stage01_skin_prep_gate.json" `
  -ReferenceFbx "$repo\source\A1角色\陆逊\陆逊绑定骨骼模型.fbx"
```

`-ReferenceFbx` 不会复制参考答案的 70 根细骨，也不会改 Stage01 Biped。它只读取参考 Skin 的逐顶点权重，把 AccuRig/CC_Base 的 twist、share、face、toe 等细分骨合并到当前 21 个游戏用 Biped 语义骨上；没有映射到的顶点才回退到 Biped 段距离规则。

生成 Skin 后可以再跑独立动作变形 smoke test：

```powershell
$repo = (Resolve-Path .).Path
& "$repo\server\batch_stage02_deform_test.ps1" `
  -SourceMax "$repo\out\stage02_runs\luxun_model__YYYYMMDD_HHMMSS_refcollapse\scene\luxun_model_stage02_skin_scene.max" `
  -AssetName luxun_model_refcollapse
```

它会测试 `bind`、`head_turn`、`left_arm_raise`、`right_elbow_bend`、`left_knee_bend`、`right_foot_roll`、`torso_twist`，每个 pose 输出 front/side/top 截图、posed `.max` 场景和逐顶点位移统计。这个测试能发现明显无跟随、顶点非法、位移爆炸等硬问题；截图仍需要按教程第四篇做人工或视觉签核。

## 输出

每次运行会写入；启用 `-ReferenceFbx` 时目录名会追加 `_refcollapse`：

```text
out/stage02_runs/<assetName>__YYYYMMDD_HHMMSS[_refcollapse]/
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

动作测试会另写入：

```text
out/stage02_deform_tests/<assetName>__YYYYMMDD_HHMMSS/
  screenshots/
    <assetName>_<pose>_front.png
    <assetName>_<pose>_side.png
    <assetName>_<pose>_top.png
  posed_scenes/
    <assetName>_<pose>.max
  reports/
    <assetName>_stage02_deform_test_report.md
  data/
    <assetName>_stage02_deform_test_report.json
```

## 当前边界

- 第一版权重是初始权重，不是商用品质最终权重。
- 参考权重压缩要求目标模型和参考 FBX 顶点顺序一致；如果拓扑不同，只能把它当作失败并回退到启发式初始权重。
- 道具/附件如果没有独立语义骨骼映射，会先按最近 Biped 段获得初始影响；炮、枪、背包、耳机等刚性道具仍需要后续专门规则或人工刷成 `1`。
- 身体、头颈、肩、腕、腿、脚需要按教程第四篇做临时动作测试和人工细刷。
- 自动动作测试只标记 smoke test 是否有硬错误，不会单独把 `deformationTestComplete` 或 `productionReady` 改成 true。
- `skinWeightsComplete=false`、`deformationTestComplete=false`、`productionReady=false` 会保持到人工/动画测试完成。

## 规则继承

Stage02 继承当前 Stage01 的生产口径：

- 只使用 Biped 作为身体 Skin 主骨架。
- `AIRA_Biped_COM` / vertical root 是控制轴，不作为身体变形骨骼加入 Skin。
- `AIRA_BONE_*` 模板骨不参与当前身体 Skin 流程。
- 没有通过 Stage01 多视图包裹性和语义确认时，Stage02 只能作为研究输出，不能进入生产交付。
