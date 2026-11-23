# Nanopublication（product-arena-09-0e8befd4，阅读14）五份独立参赛作品

挑战 [Nanopublication：科研阅读：回答问题，也给出依据](https://play.bohrium.com/challenge/product-arena-09-0e8befd4) 的五个相互独立 Skill 作品。每个目录是一个自足的可加载 Skill（SKILL.md + scripts + references + examples），五方向重心错位、零共享文件：

| 目录 | Skill | 方向重心 |
|-|-|-|
| [a-claim-atomizer](a-claim-atomizer/) | 原子断言拆解与粒度核验 | 上游拆解工程：独立可判真判据、复合谓语/限定丢失/模态升级的机检 lint、24 关系受控词表、20 条拆解样例 |
| [b-evidence-anchor](b-evidence-anchor/) | 证据锚定与原文复定位 | 证据绑定工程：源材料页/行/偏移三级索引、引文机器复定位门禁、歧义与跨行连字符处置、锚点算出不手写 |
| [c-provenance-ledger](c-provenance-ledger/) | 来源身份与可追溯台账 | 来源元数据工程：SHA-256 指纹核验、内容寻址 URI 落账、跨来源去重合并、版本对照、冲突只报不裁、TriG/JSONL 导出 |
| [d-qc-regression](d-qc-regression/) | 质量门与反例回归 | 过程质量控制：逐条对抗性核验（verdict+可复现依据）、诚实状态机、12 例已知错误合成题集回归自证 |
| [e-export-review](e-export-review/) | 结构化导出与人工复核 | 下游消费工程：严格 schema 校验、JSONL/CSV/复核单 MD/自包含 HTML 导出、独立回读交叉核验一致性 |

五者互不依赖，均可单独安装到 `/skills/weekly-skill` 使用；各目录 `examples/` 内为
**合成示例**（虚构论文/台账，目录内已标注），非正式案例结果。运行契约、输入输出、
异常处理与边界见各 SKILL.md。
