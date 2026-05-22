# Stage01 自学习自成长绑骨规范

本规范是 Stage01 绑骨工作的默认启动流程。只要任务目标是“对模型做 Biped/骨架创建、校对、修复、批量评估、和参考答案学习”，都必须启用这套流程。

它的目标不是让脚本盲目跑完，而是让 Agent 主导教程式操作：按 Root 到末端的顺序逐段建立、切片校验、局部修复、锁定通过段，并把每次失败和工具缺口沉淀成下一轮工具改进。

## 默认启动条件

遇到下列任一任务，默认启动本规范：

- 从原模型生成 Stage01 Biped 候选。
- 对已有 Stage01 run 做 CT 切片复核或失败修复。
- 和 A1 参考绑定资产做学习校对。
- 批量重跑、横向报告、抽样验证。
- 用户要求“更贴近产品级”“继续优化绑骨能力”“自学习/自成长”。

## 双轨目标

每次绑骨工作必须同时产出两类结果：

| 轨道 | 必须产出 | 判断标准 |
| --- | --- | --- |
| 资产产出 | Stage01 场景、CT 切片、wire/bone 图、状态表、报告 | 当前候选是否可解释、是否被 gate 阻断、下一步该修哪里 |
| 工具成长 | 失败案例、尝试记录、正负收益判断、工具缺口、待实现项 | 工具是否比上一轮更会发现问题、更会修局部、更少假通过 |

不能只交付候选场景而不记录工具缺陷，也不能只研究工具而不生成可复查产物。

## Agent 控制原则

- Agent 控制流程顺序、证据升级、尝试保留/回退、停止和提问。
- 脚本只负责机械能力：创建 Guide/Biped、采样 CT、局部移动、生成截图、整理报告。
- 固定迭代次数不是成功标准；成功标准是严格 CT gate、wire/bone 多视图和语义判断。
- 失败不是坏结果；无法自动修复时，要输出明确 blocker、尝试历史和需要用户/参考答案确认的问题。

## 标准操作顺序

按教程从稳定锚点到依赖末端处理。上游没过，不应大规模调整下游。

1. `Root / COM / Pelvis`
   - 确认地面、身体中心、骨盆高度、COM 控制策略。
   - CT 检查 `Pelvis->Spine`，通过后锁定。

2. `Body Center Chain`
   - Spine、Chest、Neck、Head。
   - 区分头骨、头饰、冠、发束。HeadTop/CrestTop 只做语义参考，不能拉偏 Head。

3. `Lower Body`
   - Pelvis->Hip、Hip->Knee、Knee->Ankle、Ankle->Toe。
   - 宽袍、裙摆、靴筒、裤甲不能直接当腿骨中心。
   - 左右腿分开验收，不能只靠镜像假设。

4. `Upper Body`
   - Chest->Clavicle、Clavicle->Shoulder、Shoulder->Elbow、Elbow->Wrist。
   - 袖子、护腕、手部装饰不能拉偏手臂中心线。

5. `Deferred Details`
   - 手指、武器、布料、头饰、翅膀、尾巴、挂件等记录为后续结构/Skin 问题。
   - 不允许这些细节把主 Biped 链带偏。

## 每段闭环

每处理一个骨段，都执行下面闭环：

1. 读取当前证据：CT 切片、wire/bone front/side/top、局部 crop、纹理对照、参考答案。
2. 只针对当前段提出局部修改假设。
3. 运行局部 probe 或 Max 局部修复工具。
4. 重新计算严格 CT 失败数。
5. 判断正收益、负收益或无收益。
6. 正收益且不破坏已锁段才保留。
7. 负收益立即回退，并记录为“不保留策略”。
8. 无收益时升级证据，而不是继续空转。
9. 仍无法判断时，形成问题提问。

## 证据升级规则

当局部切片失败或信息不足时，按风险从低到高尝试：

- 增加当前关节附近切片密度，例如 5 station 升级到 9 station。
- 在失败关节附近增加偏移切面。
- 适度增加 slab 厚度，只在点数不足时使用；若隐藏真实偏差则回退。
- 对照 front/side/top wire/bone 和 texture_wire_compare。
- 对照 AccuRig 参考答案骨点、骨段长度、脚/手/头语义。
- 尝试局部步长调整，例如下半身从 3.5% 身高提高到 7%-10%，但必须逐段验收。

## 停止条件

出现下列情况，不得继续假装修复成功：

- 严格 CT 失败无法继续下降。
- 加密切片暴露更多失败，说明标准切片漏检。
- 局部修复会破坏已锁定父段。
- Biped 结构约束阻止必要的节点/长度/方向变化。
- 点云只显示衣服/护甲，隐藏关节无法可靠推断。
- 参考答案和 mesh 证据冲突，需要人工决策。

停止时必须输出未解段、失败 station、尝试过的方法、每次正负收益、需要问用户的问题。

## 工具成长要求

每轮工作结束必须更新一份学习记录，至少包括：

- 哪些样本成功归零。
- 哪些样本有正收益但未成功。
- 哪些策略负收益，不能默认启用。
- 哪些证据升级有效。
- 当前脚本缺什么局部能力。
- 下一步工具应该补什么。

工具改进项按下面分类：

| 分类 | 例子 |
| --- | --- |
| measurement | 加密 CT station、关节偏移切面、失败段热力表 |
| local_edit | 单节点移动、段长调整、Toe/Wrist 端点定向调整 |
| locking | 已通过段锁定、父段退化检测、回退机制 |
| report | 正负收益表、问题清单、对比 contact sheet |
| reference_learning | AccuRig 骨点抽取、骨长/关节位置差异、语义映射 |

## 默认目录约定

| 内容 | 目录 |
| --- | --- |
| 原始 Stage01 产出 | `out/runs/<asset>__YYYYMMDD_HHMMSS/` |
| 横向视觉报告 | `report/<pack>/` |
| 自学习抽样实验 | `report/ordered_ct_probe_samples/` |
| 规范和技能 | `docs/stage01-self-learning-rigging-standard.md`、`docs/skills/stage01-ct-guided-biped-rigging/SKILL.md` |
| 工具脚本 | `server/stage01_ct_ordered_refine_probe.py` 等 |

## 最小报告模板

每轮学习报告至少包含下列结构。模板文件见 `docs/templates/stage01-learning-run-report-template.md`。

```markdown
# Stage01 Learning Run

## Scope
- Assets:
- Source runs:
- Reference assets:

## Results
| Asset | Baseline CT | Best CT | Dense CT | Status |
| --- | ---: | ---: | ---: | --- |

## Attempts
| Strategy | Asset | Before | After | Keep? | Reason |
| --- | --- | ---: | ---: | --- | --- |

## Remaining Blockers
- Segment:
- Station:
- Evidence:
- Attempts:
- Question:

## Tool Improvements
- Measurement:
- Local edit:
- Locking:
- Report:
- Reference learning:
```

## 当前已验证经验

来自 2026-05-22 抽样实验：

- `a1_001_caocao` 使用有序局部修复可从 CT `6 -> 0`，9-station 加密也可 `7 -> 0`。
- `a1_006_fazheng` 可从 CT `27 -> 1`，剩左脚趾端点径向覆盖问题，需要 Toe pivot 语义确认。
- `a1_023_zhangren` 可从 CT `14 -> 3`，剩右膝和右肘腕径向覆盖问题，需要侧/顶视、纹理和参考答案确认。
- 默认 joint backtrack 对法正是负收益，不应默认启用。
- 单纯增加迭代数不是解决方案；有效的是按段处理、锁定父段、局部步长和证据加密。
