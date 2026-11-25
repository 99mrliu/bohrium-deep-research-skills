# 科研问题驱动检索（challenge-e7598a44）五方向独立 Skill 套件（v2）

五个**相互独立、零共享文件**的 Skill bundle，面向"固定科研问题 + 有限快照 +
全记录筛查 + 九篇真实署名文献核验"的评测场景。与旧作（v1：筛查台账/问题规划/
快照检索三管线变体，best 77.67）不同，v2 五份的**重心错位**，各把重器放在检索
工程的不同环节；但每份都是能从 `/input/case.json` 走到 `/app/output/result.json`
的完整技能，动态读取 `output_contract` 全部字段、诚实三值状态（complete/partial/
blocked）、空字段必有说明。

| 目录 | 重心 | 核心机制 | 一句话立场 |
|-|-|-|-|
| [a-contract-sentinel](a-contract-sentinel/) | 过程质量控制 / 契约合规 | 契约探针 → 轻量确定性管线 → **独立八项门禁**（不过不交付） | 交付物是否合格由可复算的门禁决定，不由自我感觉决定 |
| [b-snapshot-forensics](b-snapshot-forensics/) | 上游数据真实性 | 文件指纹 + 逐文件取证 + **夹具隔离登记册** + 署名清单元数据法证（authentic/mismatch/absent），信任门之后才可筛查 | 在信任任何记录之前先做取证 |
| [c-coverage-compass](c-coverage-compass/) | 证据充分性与停止判据 | SQ×证据覆盖矩阵 + 充分性分级（sufficient/thin/starved）+ 边际收益估计 + **三态停止决定**（含 handoff_to_human）+ 缺口分类 | 检索的终点是"证据够了"或"如实转人工"，不是"查不动了" |
| [d-query-foundry](d-query-foundry/) | 术语与查询工程 | 查询族锻造（拉丁/CJK/跨语词表/连字符·单复数·缩写变体，三重预算上限）+ 逐命中位置证据 + **署名清单 known-item 召回审计**（missing 附术语/年份缺口诊断） | 查询质量用已知物召回审计证明，不用检索次数证明 |
| [e-review-studio](e-review-studio/) | 下游交付物与人工复核渲染 | 一键生成 ledger.csv(UTF-8-SIG)/report.md/自包含 review.html/**PRISMA 式 flow.svg**/manifest.json(sha256)，独立回读交叉核验（篡改必被抓） | 结果只有被人能复核、被机器能回核，才算交付 |

## 共同纪律

- 全部脚本仅 Python 3 标准库（≥3.8）、零网络；有限快照之外的世界不存在，不补造文献。
- 夹具标记（`synthetic_duplicate` / `conflict_opinion` 等）是输入事实：如实登记去向，
  冲突意见只登记为争议证据、不替其做学术裁决。
- `result.json` 含 `case_id` + 契约全部字段 + `status` + `sources` + `uncertainty`；
  空字段经 `field_notes`/uncertainty 说明原因（"没有"与"漏了"必须书面区分）。
- 预算纪律：每份 bundle 2–3 条命令即可走通，模型判断集中在个别复核环节；
  任何中断都有可交付的诚实 partial。
- 每个 bundle 的 `examples/minimal/` 为**合成示例**（虚构 DOI `10.0000/synth.*`），
  预期产物全部由脚本真实运行生成，非正式案例结果。

## 平台约束自查（提交时）

各 bundle 文件数 14–18（≤50）、最大单文件 ≤35KB（≤500KB）、总计 ≤262KB（≤2MB）、
无符号链接、全部 UTF-8 文本无二进制；SKILL.md frontmatter 仅 name/description 两键。
