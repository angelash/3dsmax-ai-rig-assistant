# 3ds Max AI Rig Assistant：Stage 01 Biped 骨架创建与匹配

这个工具对应教程第一篇：

`video-tutorials/BV1ftReBYEg3-01-biped-skeleton-and-matching.md`

第一版不是全自动绑骨，而是“Guide 定位点 + Biped 自动创建/匹配 + 多视图证据包 + Skin gate”。这样更适合真实生产：AI 或脚本负责机械流程，人或 VLM 负责结构化视觉判断，最终 gate 负责拒绝不合格候选。

## 已实现能力

脚本位置：

`F:/workspace/github/3dsmax-ai-rig-assistant/maxscript/aira_stage01_biped.ms`

功能：

| 功能 | 说明 |
| --- | --- |
| Create / Update Guides | 根据选中模型包围盒生成 Stage01 关节定位点 |
| Mirror L Guides To R | 把左侧定位点沿 X 轴镜像到右侧 |
| Create Biped From Guides | 用鲁班风格预设创建 Biped，并尝试匹配主要骨骼 |
| Fit Existing Biped To Guides | 将当前场景已有 Biped 重新贴合定位点 |
| Validate / Report | 检查缺失 Guide、左右对称问题，并生成 Markdown 报告 |
| Save Stage01 File | 另存一个 `_stage01_biped.max` 工作文件 |

离线批处理还会执行 Biped fit refinement loop：根据 Fit QC 偏差反复缩放 Biped 段长并重新定位，直到机械拟合收敛或达到上限。这个循环只解决 Biped 对 Guide 的机械一致性，不能替代 front/side/top 包裹性签核。对宽袍、裙摆、披风或靴筒遮挡腿的角色，Guide 生成会降权衣服外轮廓，用更保守的隐藏腿模板放 Hip/Knee/Ankle；视觉签核也必须确认腿链没有追衣服边。

## 使用流程

1. 在 3ds Max 2020 或更高版本打开角色模型。
2. 选择角色模型。如果角色由多个 mesh 组成，可以多选。
3. 运行脚本：

   ```text
   Scripting > Run Script > aira_stage01_biped.ms
   ```

4. 点击 `Create / Update Guides`。
5. 手动拖动 `AIRA_GUIDE_*` 定位点到模型关节位置。
6. 如果只调了左侧，点击 `Mirror L Guides To R`。
7. 点击 `Create Biped From Guides`。
8. 在 Figure Mode 中人工检查骨盆、腿、脚、躯干、手臂、脖子、头。
9. 点击 `Validate / Report` 生成检查报告。
10. 点击 `Save Stage01 File` 保存阶段文件。

## 坐标约定

第一版按这个约定生成 Guide：

| 项 | 默认 |
| --- | --- |
| 上方向 | Z |
| 左右方向 | X |
| 角色朝向 | -Y |
| Biped 创建角度 | -90 度 |

如果你的模型朝向不是 -Y，先在 3ds Max 中把模型朝向调到统一规范，或者后续改脚本里的 `facingAngle`。

## Guide 命名

中心线：

```text
AIRA_GUIDE_Root
AIRA_GUIDE_Pelvis
AIRA_GUIDE_Spine
AIRA_GUIDE_Chest
AIRA_GUIDE_Neck
AIRA_GUIDE_Head
AIRA_GUIDE_HeadTop
```

左右肢体：

```text
AIRA_GUIDE_L_Clavicle
AIRA_GUIDE_L_Shoulder
AIRA_GUIDE_L_Elbow
AIRA_GUIDE_L_Wrist
AIRA_GUIDE_L_Hand
AIRA_GUIDE_L_Hip
AIRA_GUIDE_L_Knee
AIRA_GUIDE_L_Ankle
AIRA_GUIDE_L_Foot
AIRA_GUIDE_L_Toe
```

右侧同名把 `L_` 改成 `R_`。

## 第一版边界

这版先解决第一篇的主体流程，但有几个边界：

- 手指只创建 Biped 结构，暂不逐指自动匹配。
- 不自动创建耳机、背包、枪、炮等附属 Bones；那是第二篇范围。
- Stage01 不自动添加 Skin，也不处理权重；批处理会生成 `*_stage01_skin_prep_gate.md`，说明进入 Skin 前还需要哪些人工/VLM 语义确认和权重准备。第三、四篇范围已独立为 `docs/stage02-skin-workflow.md` 和 `server/batch_stage02_skin.ps1`，不会回改 Stage01 绑骨逻辑。
- Biped 节点贴合依赖 3ds Max 的 Biped IK 和 Figure Mode，有些节点可能需要人工微调。
- 离线 MCP/批处理入口已接入，但 Max 内部桥接仍只允许白名单工具函数，不接受任意 MaxScript。

## 适合接 MCP 的安全工具函数

后续 MCP 不应暴露任意 MaxScript 执行，建议只暴露这些白名单函数：

```text
AnalyzeScene()
CreateGuidesFromSelection()
MirrorLeftGuidesToRight()
CreateBipedFromGuides()
FitBipedToGuides()
ValidateStage01()
SaveRigVersion()
GenerateStage01Report()
```

AI 负责调用这些工具和解释报告，不直接随意改场景。

## 需要后续确认的项目规范

后续如果要做成你们项目的生产工具，需要确认：

1. 角色统一朝向是 `-Y`、`+Y` 还是其他方向。
2. 角色单位是厘米、米，还是 Max 默认单位。
3. 角色模型是否要求 pivot 在脚底中心或世界原点。
4. Biped 命名前缀是否要用 `Bip001`、角色名，还是项目统一前缀。
5. 手指、脚趾数量是否固定。
6. 导出 Unity/UE 的 FBX 目录和命名规范。
7. 是否允许脚本自动移动模型到原点，还是只提示不自动改。
