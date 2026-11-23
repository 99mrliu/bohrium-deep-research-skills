# 阅读10｜文献总结与结构化笔记（product-arena-06-6d8cf72b）

本题五个**相互独立**的参赛 Skill bundle，重心错位、零共享文件，各自含完整
`SKILL.md`、`scripts/`、`references/` 与可运行的合成最小示例（标注为合成示例，
非正式案例结果）：

| Bundle | 重心 | 锚点体系 | 一句话 |
|---|---|---|---|
| [source-fidelity-notes](source-fidelity-notes/) | 上游数据真实性 | 行级 `p2-l14` | 先把 PDF 变成带保真回执的可信文本层，再写笔记 |
| [knowledge-atom-notes](knowledge-atom-notes/) | 中段知识工程 | 段落级 `s2¶3` | 类型化知识点 + 术语归一化治理 + 可检索索引 |
| [evidence-adjudicator](evidence-adjudicator/) | 证据裁定问答 | 字符窗 `c2-03` | 双侧检索 + supported/contradicted/not_reported/ambiguous 状态机 |
| [contract-pilot](contract-pilot/) | 过程质量控制 | 合同路径 | 骨架先行、预算检查点、schema 校验、诚实降级、审计轨迹 |
| [delivery-studio](delivery-studio/) | 下游渲染工程 | 工件清单 | notes.md/HTML/PNG 预览 + 复用包 + sha256 manifest + 交付核验 |

每个 bundle 的示例均为虚构论文与虚构案例，仅演示接口；真实评测由平台在
3 个固定案例上运行。提交目录根部的 `GITHUB_URL.txt` 指向本目录对应子目录。
