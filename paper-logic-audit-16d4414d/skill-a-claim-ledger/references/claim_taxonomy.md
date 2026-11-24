# 主张分类与判据（claim taxonomy）

本参考定义 claimledger 工作流中 attribution、verdict、severity 的判据。
判据的用途是让两条审查路径（不同人/不同次运行）对同一句子给出相同归类。

## attribution 四分法

| 类型 | 判据 | 典型线索 | 可否计为作者缺陷 |
|-|-|-|-|
| author_claim | 作者对本文结果或贡献的断言 | 本文/我们/本研究 + 表明、证明、显示、提出；we show/demonstrate/propose | 可以 |
| cited_view | 转述他人已发表观点 | 句内 [n]、(Name, year)、et al. + 报道/认为/指出/reported/argued | 不可；只可标"引用是否支持所转述的话"（属引用支持检查） |
| hypothesis | 作者明确标注的假设、推测、展望 | 假设/假如/若/有望/可能；hypothesize/suppose/would/may | 不可；最多给建议"补验证实验" |
| control_or_design | 对照组、基线、刻意设置的实验安排 | 对照组/阴性对照/baseline/control group | 不可；设计与矛盾必须区分 |

边界情形：同一分句先转述后发挥（"Smith 报道 X，因此我们认为 Y"）——拆成两条，
前半 cited_view、后半 author_claim。句内引用标记只是线索：作者复引自己前作支持
当前主张时，仍属 author_claim，证据是被引的前作。

## verdict 四分法

| verdict | 定义 | 必填项 |
|-|-|-|
| supported | 文中存在证据且证据强度 ≥ 表述强度 | evidence_sentence_ids |
| insufficient | 有证据但撑不住强度（"显著"无统计、"证明"只有个案、相关写成因果） | evidence_sentence_ids + 缺口说明 |
| unsupported | 无证据，或证据方向相反 | 指出相反证据句 id |
| pending | 现有材料无法确认 | note 写清缺什么（被引原文不可得/图缺失/数据未给） |

强度梯度（弱→强）：提示/可能 < 显示/表明 < 证明/证实/导致。verdict 的强度比较
在同一梯度上进行：证据停在"相关"，表述到"导致"即 insufficient。

## severity 判据

| 级 | 判据（满足其一） | 修改时限建议 |
|-|-|-|
| critical | 主结论（摘要/结论章的核心主张）unsupported 或与证据相反；方法设计回答不了研究问题 | 必须改，改前不宜投稿 |
| major | 关键中间主张 insufficient；跨章节口径冲突（摘要 vs 结果数字不一致）；因果/相关混用进入结论 | 应当改 |
| minor | 局部表述强度超标；次要主张缺引；单处术语口径漂移 | 建议改 |
| info | 不影响结论的改进建议 | 可选 |

定级三问（写进 basis）：是否影响主结论？是否可修正（补实验/改措辞/删句）？
是否影响可复现性？三问皆否不得高于 minor。

## 修改建议的可执行标准

每条建议必须落到：改哪一句（sentence_id）、怎么改（给出替换措辞或要补的证据
类型）、改完达到什么状态。反例（不可执行，禁止交付）："建议补充论证""建议加强
逻辑""建议核实数据"。正例："将 S0004 的'显著提高 40%'改为'中位寿命提高 40%
（1.0e5→1.4e5 周次，n=5/组，未做显著性检验）'，或补 Mann-Whitney 检验后保留
'显著'"。
