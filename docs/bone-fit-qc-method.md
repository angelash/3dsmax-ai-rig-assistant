# 骨骼适配自检方法

> 当前决策口径：旧的算法评分、benchmark 排序和“推荐算法”已经停用。分数只允许作为历史诊断字段保留，不能用于 Skin 放行或生产交付。Stage01 现在只输出 `tutorial_centerline_qbird` 视觉候选，用它来模拟教程里的人工看图校准；实际被编辑和进入 Skin 准备的骨架只能是 Biped。

这套工具把“骨骼是否调得好”拆成三道门，而不是只看场景里有没有骨头。

## 1. 原始资产 QC

目标是判断模型是否适合进入绑定流程：

- 几何数量、三角面数、顶点数。
- 包围盒高度、宽度、深度、是否居中、底部是否接近 Z=0。
- 材质、贴图路径、丢失贴图、绝对路径贴图。
- 是否已有骨骼、Skin、单顶点骨骼影响数、无权重点。

输出：

- `*_asset_qc.json`
- `*_asset_qc.md`

## 2. 体型识别与比例量化

Stage01 现在会在生成 Guide 前先做 mesh profile。旧的 `semantic_qbird` / `visual_semantic_qbird` / `tutorial_visual_qbird` 只保留为历史方案，不再运行生产流程；当前只允许 `tutorial_centerline_qbird` 生成视觉候选：

- 对几何顶点按高度切片。
- 计算整体高度、宽度、深度、宽高比、深高比。
- 检测最大横向展开所在高度，用于估计肩、肘、腕和手部区域。
- 检测低位横向宽度，用于估计脚掌区域。
- 使用 5/95 分位轮廓估计外轮廓，使用 25/75 分位轮廓估计主体宽度，减少装饰件和外展肢体对躯干关节点的干扰。
- `tutorial_centerline_qbird` 会在教程顺序基础上把手、肩、肘、腕放到局部肢体截面的修剪中心线，避免骨骼贴在点云表面。
- 给出体型标签，例如 `compact_q_bird_wide_body_short_legs`。

陆逊模型当前 profile：

- `widthHeightRatio = 0.914063`
- `depthHeightRatio = 0.572267`
- `maxWidthZRatio = 0.5`
- `bodyType = compact_q_bird_wide_body_short_legs`

这说明它不是标准人形，而是宽体、Q 版、短腿、横向展开很强的禽鸟角色。

输出：

- `*_body_profile.json`
- `*_body_profile.md`

## 3. 骨骼机械适配 QC

这一层只回答一个可量化问题：骨骼节点是否按当前 Guide 落到了正确位置。

当前指标：

- 必需 Guide 是否完整。
- 左右 Guide 是否围绕角色中心对称。
- 主链层级顺序是否合理，例如 Pelvis < Spine < Chest < Neck < Head。
- Biped 节点到 Guide 的距离。
- Biped 节点是否落在模型扩展包围盒内。

输出：

- `*_stage01_fit_qc.json`
- `*_stage01_fit_qc.md`

## 4. 教程顺序逐骨检查

这一层对应教程前 52 分钟里的真实操作顺序，不再只看手部或轮廓覆盖：

1. 根据体型决定骨骼规格。当前陆逊模型识别为 `compact_q_bird_wide_body_short_legs`，使用 2 节脊椎、1 节短脖子、3 段腿、1 节脚趾。手部在点云里是紧凑手团，默认不展开手指链；如果后续看到清晰四指，再切换四指 Guide。
2. 从骨盆/身体中心开始检查。
3. 检查腿、膝盖、脚踝、脚掌和前脚掌方向。
4. 检查躯干侧面姿态和大头短脖子。
5. 检查锁骨、肩、肘、腕、手团。
6. 检查每段 Biped 骨段的位置、长度比例、方向规则、显示粗细和左右镜像。

输出：

- `*_rig_detail_review.json`
- `*_rig_detail_review.md`

## 5. 语义可信度门

机械分高不代表可以直接进生产。当前 Guide 是按模型包围盒估出来的，只能提供粗初值。

所以报告里会单独给：

- `stage01CandidateAvailable`
- `semanticSkinReady`
- `stage01HandoffReady`
- `productionReady`

规则是：

- 如果视觉候选缺少 Biped 贴合报告、截图或语义复核数据，`stage01CandidateAvailable = false`。
- 如果 Root、HeadTop、手部、脚掌 pivot 等语义风险没有解决，`semanticSkinReady = false`。
- 如果还没有人工确认语义关节点，`stage01HandoffReady = false`。
- 只有完成语义确认、Skin、权重、影响数、无权重点和变形测试，`productionReady` 才可能为 true。

## 6. Stage01 到 Skin 的前置门

`server/stage01_skin_prep_gate.py` 会把四类报告合并成一个 Skin 前置交付判断：

- `*_stage01_fit_qc.json`
- `*_visual_qc.json`
- `*_rig_detail_review.json`
- `*_stage01_rig_asset_qc.json`

输出：

- `*_stage01_skin_prep_gate.json`
- `*_stage01_skin_prep_gate.md`

这个报告区分四种状态：

- `stage01CandidateAvailable`：Biped 贴合报告、视觉截图和逐骨/语义报告都已生成，说明有候选可看。
- `semanticSkinReady`：Root 控制轴、HeadTop、手部细节、脚掌 pivot 等语义阻塞项已经解决。
- `stage01HandoffReady`：在候选可用、语义阻塞项解决、人工确认完成后，才允许交给绑定师进入 Skin 准备。
- `skinSetupReady`：在 `stage01HandoffReady` 基础上，才允许添加 Skin 和骨骼列表。
- `productionReady`：必须等 Skin、权重、影响数、无权重点、贴图路径和变形测试都通过后才会为 true。Stage01 自动骨架不会单独给出生产可交付结论。

当前自动批处理默认不会传入人工确认标志，所以即使旧 JSON 字段里保留了诊断分数，`stage01HandoffReady`、`skinSetupReady` 和 `productionReady` 仍会保持 false。报告会列出人工清单：身体中心链、腿/脚 pivot、锁骨/肩肘腕/手团中心线、短脖子大头、以及需要延后的冠饰、喙、布料、武器、翅膀或手指细节骨。

## 7. 本地视觉轮廓自检

当前已增加第一版视觉自检，但它不是外部视觉大模型。

流程：

- MaxScript 导出 `*_visual_snapshot.json`，包含 mesh 点云、Guide、Biped 节点/骨段和包围盒。
- `server/visual_qc.py` 生成前视图、侧视图、顶视图 PNG。
- 脚本检查宽高/深高比例、Guide 上下顺序、左右对称、Guide 离模型投影轮廓的距离、手部中心线覆盖和手臂截面中心线覆盖。
- PNG 中红色/紫色十字表示视觉目标点，连线表示 guide 到目标点的偏差。
- 输出 `*_visual_qc.json` 和 `*_visual_qc.md`。

这一步能把“看起来是否明显错位”变成可复查的截图和问题清单，也能给后续视觉大模型复核提供稳定输入。它仍不能替代人工确认语义关节点。

## 8. 视觉语义证据包

`server/visual_review_pack.py` 会把视觉快照、Visual QC、逐骨检查和 Skin gate 整理成 `visual_review/`：

- `full/`：前、侧、顶全局证据图。
- `regions/`：head、pelvis、left/right hand、left/right foot 局部裁剪。
- `review_input.md`：人工或 VLM 需要查看的证据和问题。
- `review_schema.json`：结构化审查输出 schema。
- `semantic_visual_review_template.json`：待填写的审查结果模板。

这一步仍不产生分数，只服务于语义 blocker 判断：Biped COM/Pelvis 是否只做控制轴、HeadTop 是否是冠饰、手部是否需要 Biped 手指/细节结构、脚掌 pivot 是否能从 side/top 视图确认。

## 陆逊模型当前结论

当前查看 `luxun_model_tutorial_centerline_qbird` 最新 run，Stage01 的目标口径已经改成单骨架流程：

- `AIRA_Biped_COM`：唯一被创建、校准和准备进入 Skin 的 Biped 骨架。
- `AIRA_BONE_*`：不再由 Stage01 生成；如果历史场景里存在，会被 Biped-only 批处理清理掉。

旧的七算法 benchmark 结果已经停用，不再作为“推荐”或“排名”。`tutorial_centerline_qbird` 现在只是唯一视觉候选生成器；它生成的 Guide 用来按教程顺序校准 Biped，而不是生成第二套普通 Bones。

当前关键结论不是分数，而是阻塞项：

- Biped COM 需要明确为 control-only non-deforming，身体权重从 Biped Pelvis 开始。
- HeadTop 可能被冠/头饰极值拉高，需要确认是头骨体积还是饰件。
- 单块手部质量需要确认是否要拆手指/爪/武器 detail。
- 脚掌/Toe pivot 必须用 side/top 视图签核。
- 原模型仍有贴图、Skin、权重和变形测试未完成。

Biped 的位置设置会受到 IK/层级约束影响，所以自动产线不能只相信写入坐标。正确做法是像教程一样反复用前/侧/顶视图检查，再用视觉截图和 Semantic Skin Review 做人工签核。

## 改进方向

### 短期

- 只保留 Biped 作为 Stage01 骨架；Guide 是视觉校准目标，不是第二套骨骼。
- 自动产线只移动/检查 Biped 节点，禁止生成 `AIRA_BONE_*` 模板骨骼链。
- 在 Max 里人工调整 Guide 后重新拟合 Biped 和 QC。
- 通过报告阈值拦截不合格资产，不进入 Skin。

### 中期

- 增加项目角色模板，例如禽鸟四头身角色、武器角色、带翅膀角色。
- 继续改进 `tutorial_centerline_qbird` 的主体分离、截面中心线目标和网格切片：
  - 按高度切片找头、胸、胯、脚底。
  - 按左右宽度变化找肩、肘、腕、膝、踝。
  - 根据模型朝向和轮廓判断前后脚掌、嘴部、翅膀。
  - 将披风、头饰、武器等高离群组件从主体统计中降权。
- 增加截图/视图辅助校验，让 AI 或人工按前、侧、顶视图检查 Guide。

### 长期

- 用视觉大模型或 3D landmark 模型参与 Guide 标注，但仍只让它调用白名单工具。
- 对标准人形/动物可以研究 RigNet、UniRig 类自动 rigging；对 A1 这种 Q 版禽鸟三国角色，建议作为辅助参考，不作为直接交付结果。
- 训练或沉淀项目内角色模板和失败案例，让 AI 更像绑定师一样判断 Biped 结构参数和人工关键点。
