# strength-lexicon.md — 证据强度分级与过强词表

本文件定义两级东西：(1) claim 的 strength 分级语义；(2) 机器可读的
过强词表（overclaim lexicon），被 `scripts/anchor_audit.py` 的强度措辞门
直接解析——`<!-- LEXICON:BEGIN -->` 与 `<!-- LEXICON:END -->` 之间
一词一行（`#` 开头为注释）。改动词表即改动门控，请同步更新示例。

## 1. 强度分级语义

| strength | 适用情形 | 页上措辞纪律 |
|-|-|-|
| `established` | 论文主结论、多组独立证据支撑、作者明确断言 | 可用陈述句，但仍须绑定 verified 锚点；数字逐字。 |
| `preliminary` | 单组数据、作者自陈"初步/待验证"、样本量小 | 必须用探索性措辞（suggests / indicates / 初步显示）；**禁用词表内任何过强词**。 |
| `contextual` | 背景、动机、他人工作、领域共识转述 | 只陈述可锚定事实，不下本工作的结论；**禁用词表内任何过强词**。 |

分级错配是学术汇报的高发失信点：把初步结果讲成定论，被追问时无法收口。
强度措辞门把这条纪律做成机检：`preliminary`/`contextual` 的
`slide_text` 命中词表即 `strength_overclaim`（exit 1）。

## 2. 过强词表（机器可读区）

匹配方式：NFKC + casefold + 空白压缩后做词边界匹配（中英文均可）。
收录原则：断言"证明/定论/必然/根除"类动词与副词；不收录 "show/report"
这类中性动词，也不收录强度档名本身（如 established）。

<!-- LEXICON:BEGIN -->
prove
proves
proven
conclusive
conclusively
definitive
definitively
establishes
guarantees
guaranteed
eliminates
eliminated
settles
undeniably
no doubt
证实
证明了
确立
确立了
定论
根除了
<!-- LEXICON:END -->

## 3. 改写建议（门控开火后的修复路径）

- `This proves X` → `Early data suggest X` / `初步数据提示 X`。
- `conclusively demonstrates` → `is consistent with` / `与……一致`。
- `eliminates the failure mode` → `reduces the observed failure rate`。
- 若证据确实够强：把 strength 升为 `established` 并在 notes 说明依据，
  而不是靠措辞硬撑。
