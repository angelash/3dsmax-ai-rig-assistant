# BV1ftReBYEg3 鲁班七号骨骼绑定教程目录

资料来源：

- 视频：原始视频仍保存在 `F:\workspace\open-share\video-downloads\BV1ftReBYEg3\`
- 逐字稿：`transcripts/BV1ftReBYEg3_transcript_cleaned.txt`
- 截图目录：`assets/BV1ftReBYEg3`

说明：所有教程截图都使用 HTML 图片标签控制显示宽度，例如 `width="720"`，避免在 Markdown 预览里占据过大面积。

## 文档分篇

| 篇章 | 时间范围 | 文档 |
| --- | --- | --- |
| 01 | `00:00:00 - 00:52:00` | [Biped 骨架创建与匹配](BV1ftReBYEg3-01-biped-skeleton-and-matching.md) |
| 02 | `00:52:00 - 01:32:20` | [附属骨骼与约束连接](BV1ftReBYEg3-02-prop-bones-and-constraints.md) |
| 03 | `01:32:20 - 01:55:30` | [Skin 设置与道具权重](BV1ftReBYEg3-03-skin-setup-and-prop-weights.md) |
| 04 | `01:55:30 - 02:15:25` | [身体权重与最终检查](BV1ftReBYEg3-04-body-weights-and-final-check.md) |

## 学习顺序

1. 先完成 Biped 创建、参数设置、关节点匹配。
2. 再给耳机、背包、枪、炮弹等附属装备创建 Bones。
3. 建立 Bones 与 Biped 的链接或约束关系。
4. 给模型添加 Skin，并添加所有需要参与蒙皮的骨骼。
5. 先处理炮弹、炮管、枪、背包、耳机这类简单刚性道具权重。
6. 最后处理身体、头颈、四肢的复杂权重，按测试动作反复修正。

## 截图使用

截图已按视频关键操作抽取到 `assets/BV1ftReBYEg3`，每张图宽度约 1280 像素，文档中显示宽度控制为 720 像素。需要更大图时，可以直接打开原始 jpg。

## 自动化工具

第一篇的 Biped 骨架创建与匹配已开始做 MaxScript 工具化原型：

- [3ds Max AI Rig Assistant](../../README.md)
- [Stage 01 使用流程](../stage01-workflow.md)
- [骨骼适配自检方法](../bone-fit-qc-method.md)
- [MCP 接入与运行](../mcp-setup.md)
- [后续 MCP 工具契约草案](../mcp-tool-contract.md)
