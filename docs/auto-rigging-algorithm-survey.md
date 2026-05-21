# 自动骨骼匹配方案：当前策略

> 当前结论：旧的多算法 benchmark、qualityScore 排序和“推荐算法”流程已经停用。它们在陆逊模型上给出了反向激励，会把看似高分但语义不可靠的骨架推到前面。生产链路只保留 `tutorial_centerline_qbird` 作为视觉候选生成器，再用截图、Semantic Skin Review 和人工语义确认决定是否进入 Skin。

## 当前生产链路

1. 用 `tutorial_centerline_qbird` 生成一套 Stage01 视觉候选。
2. 生成 front / side / top 视觉截图和 `views/<view>.md` 索引。
3. 运行 `visual_review_pack.py`，生成全局证据图、头/手/脚/骨盆局部裁剪和结构化审查 schema。
4. 运行 `rig_detail_review.py`，输出逐骨诊断和 Semantic Skin Review。
5. 运行 `stage01_skin_prep_gate.py`，只根据语义阻塞项、人工确认、Skin/权重状态判断交付门。
6. 旧 JSON 里的 `mechanicalScore`、`visualScore`、`detailScore`、`qualityScore` 等字段只保留为兼容诊断数据，不作为推荐、不显示为结论、不改变 `productionReady`。

## 已屏蔽的本地算法

| 算法 | 当前状态 | 说明 |
| --- | --- | --- |
| `bbox_humanoid` | disabled_legacy | 标准人形包围盒基线，不适合 Q 版禽鸟角色。 |
| `mesh_profile` | disabled_legacy | 体型 profile 有参考价值，但不能直接作为骨架方案。 |
| `qbird_profile` | disabled_legacy | A1 禽鸟模板调参历史方案。 |
| `semantic_qbird` | disabled_legacy | 机械拟合基线，容易误导手臂/手部中心线。 |
| `visual_semantic_qbird` | disabled_legacy | 曾修正手部外沿，但肩肘腕语义仍不稳定。 |
| `tutorial_visual_qbird` | disabled_legacy | 上一版表面点云目标，容易贴轮廓边缘。 |
| `tutorial_centerline_qbird` | visual_candidate_only | 唯一允许入口，只生成候选，不凭分数放行。 |

## 仍保留的诊断工具

| 工具 | 用途 | 决策口径 |
| --- | --- | --- |
| `visual_qc.py` | 生成前/侧/顶截图、轮廓和目标点。 | 只提供视觉复核输入；分数隐藏且诊断-only。 |
| `visual_review_pack.py` | 生成全局证据图、局部裁剪和结构化审查模板。 | 给人工/VLM 做 blocker 审查；不产生分数。 |
| `rig_detail_review.py` | 按教程顺序逐骨检查，并列出语义 Skin 风险。 | Semantic Skin Review 可以阻塞 Skin；旧 detail score 不参与决策。 |
| `stage01_skin_prep_gate.py` | 汇总候选、截图、语义风险、Skin/权重状态。 | 生产交付只看 gate 状态和阻塞项。 |
| `skeletor_probe.py` | 外部几何骨架探测。 | 研究性参考；当前模型分件太多，不作为生成入口。 |

## 历史归档

旧 benchmark 目录和 `default_recommended/` 只保留为历史材料。相关脚本默认会报错：

```powershell
F:\workspace\github\3dsmax-ai-rig-assistant\server\benchmark_luxun_algorithms.ps1
F:\workspace\github\3dsmax-ai-rig-assistant\server\check_algorithm_default.ps1
F:\workspace\github\3dsmax-ai-rig-assistant\server\promote_recommended_algorithm.ps1
F:\workspace\github\3dsmax-ai-rig-assistant\server\list_algorithm_benchmarks.ps1
```

如果只是研究旧实验，可以显式加研究参数汇总历史：

```powershell
F:\workspace\github\3dsmax-ai-rig-assistant\server\list_algorithm_benchmarks.ps1 -LegacyScoringResearchOnly
```

这个输出不能作为默认推荐或 Skin 放行依据。

## 外部方案判断

| 方案 | 核心思路 | 当前判断 |
| --- | --- | --- |
| Pinocchio | 给定通用骨架，自动嵌入 mesh 并计算权重。 | 可做离线适配器研究，但不进入当前主链路。 |
| RigNet | GNN/深度网络预测 skeleton 和 skinning weights。 | 依赖和许可证边界较重，只适合研究分支。 |
| UniRig | Transformer 预测多类 3D 模型骨架/权重。 | 可作为外部候选来源，但仍必须经过同一套视觉语义 gate。 |
| CGAL Mean Curvature Skeleton | 几何曲骨架/中轴线抽取。 | 更适合清理后的连续主体 mesh；当前陆逊模型分件太多。 |
| Auto-Rig Pro / AccuRig / Mixamo | 商业/闭源自动绑定。 | 可人工横向对比，不作为仓库内自动执行入口。 |

## 陆逊模型当前结论

陆逊是宽体、Q 版、短腿、横向展开强的禽鸟角色。通用自动 rigging 很容易把头饰、披风、武器、翅膀或手部团块当成主肢体，所以数值评分会制造假信心。

现在应打开最新的：

```text
F:/workspace/github/3dsmax-ai-rig-assistant/out/runs/luxun_model_tutorial_centerline_qbird__*/README.md
```

重点看：

- `screenshots/` 和 `views/front.md|side.md|top.md`。
- `visual_review/review_input.md` 和 `visual_review/regions/*.png`。
- `reports/*_rig_detail_review.md` 的 Semantic Skin Review。
- `reports/*_stage01_skin_prep_gate.md` 的阻塞项。

当前不能直接进生产的原因：

- Root->Pelvis 需要明确为 control-only non-deforming。
- HeadTop 可能被冠/头饰极值拉偏，需要确认或拆 detail bone。
- 单块手部质量需要确认是否拆手指、爪或武器 detail。
- 脚掌/Toe pivot 必须用 side/top 视图签核。
- 原模型尚未完成 Skin、权重、贴图路径和变形测试。

## 后续方向

- 不再让旧评分选择方案。
- 继续改进截图组织、语义风险识别和人工签核清单。
- 后续可以接 VLM 看 front/side/top 截图，但它也只能给语义审核意见，不能直接把 `productionReady` 置 true。
- 若引入 UniRig、RigNet 或其他外部候选，也必须走同一套视觉语义 gate。

## 参考资料

- UniRig 官方仓库：<https://github.com/VAST-AI-Research/UniRig>
- RigNet 官方仓库：<https://github.com/zhan-xu/RigNet>
- CGAL Surface Mesh Skeletonization 文档：<https://doc.cgal.org/latest/Surface_mesh_skeletonization/index.html>
- MIT CSAIL Pinocchio 介绍：<https://www.csail.mit.edu/node/6168>
