---
name: trend-claims-recompute
description: 用于文献综述/研究前沿类任务中需要写出“时间趋势”结论的场景。本技能提供从语料归一、年度切片、泊松变点/波动重算到“主张—统计”审计的完整流水线：报告中每一句上升/下降/拐点/爆发主张都必须能被重算数字支撑，矛盾主张会被审计器以非零退出码拦下。它不做因果归因、引文网络分析或语料窗口外预测，也不替代主题演化、代表作遴选与研究空白论证（但给出这些环节的强制流程）。
---

# trend-claims-recompute：时间趋势的统计严谨性——重算与主张审计

## 1. 定位

本技能的重心：**趋势章节的可信度等于其可重算性**。任何一句「上升 / 下降 / 拐点 / 爆发 /
退潮」都必须能由脚本从语料重算出的年度统计支撑，且存在一个检查器可以**证伪**与数字矛盾的
主张（`claim_audit.py` 对违规主张以退出码 1 拦停流水线）。核心纪律：

- 区分泊松噪声波动与真实变点：单年尖峰先按波动假设检验（MA z 分数），变点必须经两段
  泊松模型的 rate-ratio 95% CI 排除 1 才可写「显著」。
- 永远不把右删失的末年读作衰退（40% 规则标记 partial_year_suspect，删失 bin 不参与速率估计）。

本技能直接杀死三个反模式：**把检索前排当年份分布**（不读真实文件、拿检索顺序充数）、
**把单年尖峰当拐点**（fluctuation_as_inflection 违规）、**把右删失当退潮**
（censored_year_as_decline 违规）；同时它强制走完整四交付物流水线（时间趋势、主题演化、
代表作、研究空白），不止做趋势一段。

## 2. 固定路径

- 技能脚本：`/skills/weekly-skill/scripts/{build_corpus,slice_stats,changepoint,claim_audit}.py`
- 参考文档：`/skills/weekly-skill/references/{statistics_notes,claims_schema}.md`
- 输入：`/input/case.json`、`/input/task.md`、文献材料文件（json/jsonl/csv/bib/ris/txt/md，可能有 PDF）
- 工作目录：`/app/work`（canon.jsonl、slices.json、changepoints.json、claim_audit.json 等中间产物）
- 交付：`/app/output/`，其中 `result.json` 必须含 case_id 与 case.json `output_contract` 列出的**全部**字段

PDF 材料：先用平台提供的 pdf-text/pdf-render/ocr 工具抽文本，落盘为 .txt/.md 后再喂给
build_corpus.py；**必须读真实文件内容，不得从文件名/标签臆断**。

## 3. 执行协议

### 第 0 步 读契约 + 建档

1. 读 `/input/case.json`：记录 `case_id` 与 `output_contract` 的**每一个字段名**；读 `task.md`。
2. 定位 `/input` 下的材料文件（按扩展名盘点，PDF 先抽文本）。
3. **立刻**写 `/app/output/result.json` 骨架：case_id + 每个 output_contract 字段的占位 +
   `status` + `provenance`（输入文件清单、时间）。之后每完成一步回填一处。
4. 若没有任何可用语料：`status = blocked_no_corpus`，写明缺什么、尝试了什么，**禁止编造**。

### 第 1 步 语料归一

```
python3 /skills/weekly-skill/scripts/build_corpus.py --work /app/work --inputs /input [更多文件/目录]
```

- 产物：`canon.jsonl`（id,title,year,venue,abstract,source_file）+ `corpus_meta.json`。
- 年份缺失比例 > 20%（meta 中 `year_missing_gt_20pct` 告警）：在 result.json 的 uncertainty
  中附覆盖度说明，**禁止把缺失年补零**。
- 若已有其它语料审计技能产出的 canon.jsonl，可直接复用（跳过本步）；本脚本可独立运行。

### 第 2 步 年度切片

```
python3 /skills/weekly-skill/scripts/slice_stats.py --work /app/work            # 年度
python3 /skills/weekly-skill/scripts/slice_stats.py --work /app/work --window 2 # 跨度<8年时用窗
```

产物 `slices.json/csv`：每个 bin 的计数 + 泊松 95% CI（garwood-wilson-hilferty），
以及 `partial_year_suspect`（末 bin 计数 < 40% × 前 3 bin 中位数 ⇒ 疑似右删失）。

### 第 3 步 变点与波动

```
python3 /skills/weekly-skill/scripts/changepoint.py --work /app/work
```

产物 `changepoints.json`：全部候选 τ（lambda1/lambda2/rate_ratio/CI/ll_gain/rank/supported）、
`adopted_tau`、fluctuations（MA z≥2 的单年波动）、warnings。**采纳规则：只有 rate-ratio CI
排除 1 的候选，报告才允许写「显著变点」**；删失末 bin 已被自动排除。

### 第 4 步 主张审计（定稿前，强制）

1. 从趋势章节草稿中提取每条趋势句为一条主张，写 `/app/work/claims.json`
   （schema 见 `references/claims_schema.md`：claim_id/kind/year 或 year_range/direction/
   significance/statement）。
2. 运行：

```
python3 /skills/weekly-skill/scripts/claim_audit.py --work /app/work --claims /app/work/claims.json
```

3. **退出码 1 = 有违规，必须改主张后重跑，禁止绕过**。四类违规：
   `censored_year_as_decline`（拿删失年末年当衰退）、`unsupported_changepoint`
   （CI 未排除 1 却写显著变点）、`fluctuation_as_inflection`（单年尖峰当拐点）、
   `direction_mismatch`（方向与重算计数相反）。downgraded 的主张在报告中降级为
   探索性表述并说明统计功效不足。

### 第 5 步 主题演化（无脚本，流程强制）

- 从 canon.jsonl 的 title+abstract 建**术语队列（term cohorts）表**：行=术语，列=年份
  （或 2–3 年期段），值=出现文档数/占比；同义词先归并（人工列映射表）。
- 据此分三类写演化：**涌现**（某期段后从 0/近 0 到持续出现）、**衰退**（反向）、
  **漂移**（同一术语共现对象/子任务发生变化）。
- 每条演化主张必须写明 **何时**（期段）+ **为何是变化**的证据：队列计数对比 +
  ≥2 个 canon id 例句；「新兴主题」必须是新语义单元，**禁止把旧词换说法充数**
  （归并映射表就是反驳证据）。

### 第 6 步 代表作遴选（无脚本，流程强制）

- 按第 3 步的变点把语料划分为若干阶段（如 adopted_tau 前后），**每阶段都必须有代表作**，
  不允许任何阶段空缺。
- 阶段内多准则打分（建议表：被引、venue 质量、方法新颖性、被后续工作沿用程度、主题覆盖），
  被引**在阶段内归一化**（早期论文不与晚期论文比原始被引），杜绝「引文 top-N 充代表作」。
- 每篇入选写一句**选择口径说明**（为什么是它而不是同阶段高被引替代品）；落选的
  高被引近邻列为准入/排除备注。

### 第 7 步 研究空白（无脚本，流程强制）

- 每条空白主张必须附**排除证据**：(a) 检索范围说明（用了哪些库/词/年份段、命中量）；
  (b) **近失分析（near-miss）**：列出最接近该空白的 3–5 篇 canon 记录，说明它们各自
  「差在哪一点」所以不构成覆盖。
- **禁止把「没检索到」直接当空白**；区分「真空白」「本语料覆盖不到（范围外）」
  「已有工作但极薄弱」三种，后两者必须如实标注。

### 第 8 步 证据回链与定稿

- 报告每条主张挂两类证据：canon id 列表 + 支撑它的统计量（CI / rate_ratio / ll_gain / z /
  队列计数），并写明出自哪个工件（slices.json、changepoints.json、claim_audit.json）。
- 写 `/app/output/trend_report.md`（或 contract 指定文件名），回填 result.json 全部字段，
  把 slices/changepoints/claim_audit 的 JSON 一并拷入 /app/output 供复核。

## 4. 输出契约

`result.json` 必含：`case_id` + output_contract **全部字段** + `status`
（`ok` / `partial` / `blocked_*`）+ `evidence`（工件路径与关键数字）+ `uncertainty`。
部分完成时：已完成的交付物写全，未完成的写明卡在何步、缺什么数据、已尝试什么——
诚实 partial 远好于编造 ok。

## 5. 预算规划（64 请求 / 900 s）

- 第 0–4 步（脚本流水线）约 8–12 次请求：脚本一次跑通的设计，失败先读 stderr 再修。
- 第 5–7 步是模型工作大头：预留 35–45 次请求；术语队列先在 canon 上用一次 grep/脚本
  预聚合再读，避免逐篇通读烧请求。
- 第 8 步与复核留 8–10 次；任何时候剩余 <10 次请求时，立即停止扩展性分析，保底回填
  result.json（partial 优先）。

## 6. 异常处理

| 异常 | 处置 |
|---|---|
| 无语料 / 输入全不可解析 | `status=blocked_no_corpus`，列尝试过的文件与失败原因，不编造 |
| 年份缺失 >20% | 补零禁止；trend 结论附覆盖度 uncertainty；必要时按有年份子集出 partial |
| 末年为右删失（partial_year_suspect） | 删失 bin 排除出速率/变点估计；衰退主张须用未删失区间证据，否则审计违规 |
| 单年尖峰 | 走波动清单（z≥2）；无 supported 变点时只能写「波动」，写「拐点」必被判违规 |
| 有效跨度 <8 年（bin） | changepoints.json 出 `span_lt_8` 告警；改用 --window 聚合；一切变点结论标「探索性」 |
| 日期口径敏感（print vs online 年） | 两种口径各跑一次 slice_stats+changepoint，报告取**保守交集**（两种口径都支持的结论才写死） |
| claim_audit 退出 1 | 逐条按违规码修主张（删/降级/换 τ）后重跑；禁止删审计器或改退出码 |
| 脚本异常退出 | 先读 stderr 与输入 schema（canon.jsonl 是否缺 year 等），修数据不修判定逻辑 |

## 7. 不适用

- 不做**因果归因**（为什么升/降只能作假设性讨论并标注）。
- 不做**引文网络/共被引分析**（无图算法组件）。
- 不做语料窗口外的**预测**（不外推未来年份）。
- 超大语料（数十万级）的分布式 ingest 不适用；本归一器面向单任务中小规模语料。

## 8. 合成示例

`examples/` 内置**全合成**语料（77 条，已标注 synthetic/合成），植入 2018 速率变点、
2014 单年尖峰、2025 右删失末年；`bash examples/run_example.sh` 一次跑通 GOOD/BAD 两组
主张审计并自证四种违规全部触发，真实产物在 `examples/example_output/`。
