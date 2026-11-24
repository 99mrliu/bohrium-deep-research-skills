# narrative-first-deck 叙事规则参考

本文件是 plan_lint.py 七条规则的语义说明，供 Agent 编辑 storyline.json / slide_plan.json 时对照。

## 1. Claim 图语义（storyline.json）

- **mainline**：四句话主线——problem（什么问题、为什么难）、method（怎么做的）、
  results（关键数字是什么）、limitations（边界在哪）。写进封面页备注，作为全场讲述的锚。
- **claims**：有序列表，必须按 problem → method → results → limitations 排列。
  每条 claim 是**一句话可以讲清的主张**，字段：
  - `id`：c1, c2, … 被 slide_plan 的 `claim_id` 引用；
  - `text`：主张文本（页面上的"主张："行应与之一致）；
  - `evidence_refs`：证据锚点数组，`{type: page|figure|table|section, ref, quote}`。
    ref 形如 `p.4` / `Figure 2` / `Table 1` / 章节标题；quote 是源文逐字片段（供复核）；
  - `depends_on`：叙事依赖。被依赖的 claim 必须排在依赖者之前讲（lint 强制）。

## 2. 页型覆盖（R1）

六类页型必须齐备：title / background / method / results / discussion / conclusion。
results、discussion 可有多页，其余通常一页。缺任何一类 → fail。

## 3. 一页一个主张（R2）

每页恰好一个 `claim_id`，且必须命中 storyline 中的 claim；一个 claim 不得被多页复用；
页面 claim 文本与 storyline 不一致 → warn；storyline 中存在未上页的 claim → warn。

## 4. 证据锚定（R3）与图-主张绑定（R4）

- 每条 claim 至少 1 个 evidence_refs；每个锚点必须能解析到抽取源：
  页码 ≤ 论文页数；Figure/Table 标签在 source_index.json 中真实存在；章节标题在全文可命中。
  quote 未逐字命中 → warn（PDF 抽取断行可能造成误报）。
- **绑定规则**：页面 `figures` 展示的 Figure N，必须出现在该页 claim 的 figure 类
  evidence_refs 中（图上页 = 为某一主张作证）；results 页 claim 引用了图但页面没放 → warn。

## 5. 顺序规则（R5）

页面 claim 序列必须满足：
1. 按 storyline claims 列表序非递减（不许"讲完结果回头讲方法"）；
2. 依赖闭包在前：claim A depends_on B，则 B 所在页必须先于 A 所在页。
违反 → fail，报告精确到 slide 编号与 claim id。

## 6. 计时模型（R6）与其不确定性

- **时长来源优先级**：storyline.duration_min > task.md 解析值（`duration: N minutes`/`N 分钟`）> 缺省 12 min。
- **语速模型**：中文（CJK 字符，含中文标点）≈ 4 字/秒；英文单词与数字 token ≈ 2.2 词/秒；
  混合文本分段计数相加。模型出处：常见中文汇报口播 220–260 字/分钟、英文约 130 词/分钟，
  取整为便于心算的常数。
- **判定**：逐页秒数 = notes 估计值；总和须落在 duration×60×(1±15%) 区间内，
  超出 → fail 并列出最长的三页；所有页 notes 为空 → warn（无法校验）；个别页 notes 空 → warn。
- **不确定性**：真实口播受语速波动、停顿、翻页、现场提问影响，估计误差可达 ±20–30%，
  故判定阈值取 ±15% 并在 result.json 的 uncertainty 中声明；不要把估计值当作精确计时。

## 7. 数字逐字（R7）

bullets 中出现的每个数字 token（含小数与 %）必须在论文抽取全文或该页 evidence quote
中**逐字**出现。找不到 → fail（精确到 slide 与 bullet）。这是"找不到出处的内容不上页"
的机器化执行。注意：notes（讲稿）不做此校验——口头展开允许转述，页面文字必须忠实。

## 8. Lint 判定语义

- `pass`：规则完全满足；`warn`：存在风险但不阻塞构建（会进入 result.json 的 uncertainty/
  并使 status=partial）；`fail`：违反硬性叙事约束，plan_lint.py 退出码 1，**不构建 deck**。
- 报告：`/app/output/plan_lint_report.json`（七条规则逐条判定、计时表、违规页清单），
  被校验的 storyline 同时复制为 `/app/output/storyline.json` 供复核。
