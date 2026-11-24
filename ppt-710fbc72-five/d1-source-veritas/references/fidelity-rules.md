# Fidelity Rules — source-veritas-deck 核验规则

本文件定义语料台账（source corpus ledger）与逐条断言核验（per-claim
verification）的完整规则。核心信条：**宁可少写，不可无据**。

## 1. 语料台账（corpus ledger）

`extract_source.py` 把论文 PDF 解析为 `work/corpus/corpus.jsonl`，每行一条：

- `kind=text`：`{id, page, bbox, text, sha256, numbers[]}`。
  `text` 为空白归一化后的文本块；`sha256` 是对该文本的哈希；`numbers`
  是该块内全部数字 token 的清单。
- `kind=figure`：`{fig_id, page, bbox, label, file, sha256}`。
  图以两种途径获取：PDF 内嵌位图原样导出（不重采样）；矢量图按
  "Figure N" 图题所在区域渲染成 PNG。`sha256` 是文件字节级哈希。
- `kind=section`：检测到的章节标题（常见章节名 / 编号标题 / 大字短行启发式）。

台账是**唯一事实来源**：下游任何内容必须引用台账条目，禁止下游环节重新
解析 PDF、重新渲染图片或从记忆中补写数字。

## 2. 数字 token 与归一化

数字 token 由正则抽取：整数、千分位、小数、负数，可带相邻单位
（% ％ ms s min h hours GB MB KB Hz eV K °C μm nm mm cm m km g kg mg mL L x × pp pt 等）。

- 归一化形式：拆成 `core`（数字本体，如 `92.4`）与 `unit`（如 `%`）。
- 逐字判定：`core` 必须以"数字边界"出现在语料文本中——前后不得粘连其他
  数字或小数点（即 `92.4` 命中 `accuracy of 92.4%`，但不命中 `192.44`）。
- 比较前对语料与被检文本做**空白归一化**（连续空白折叠为一个空格），
  不因换行/多空格而误判，但数字字符本身一个都不能差。

## 3. 判定语义（verdict）

对每条 bullet / claim / 图 / 证据引用，逐条给出 verdict：

| verdict | 含义 |
|-|-|
| `verified` | 数字逐字出现在**该页证据锚点**（evidence refs 指向的页/图/引文）对应的台账条目中；或图文件与台账 sha256 字节一致；或引文是原文逐字子串。 |
| `loose` | 数字存在于语料但**不在锚定条目**里（锚点松）；或该页根本没有证据锚点，只能全语料兜底。内容保留，但在 fidelity_report.json 中显式标记，提示 Agent 补锚点。 |
| `unverified` | 数字在语料中**完全不存在**；或证据 ref 无法解析到台账条目；或图文件缺失 / sha256 与台账不符（被静默重渲染或替换）；或引文不是原文逐字子串。 |

slide 级 verdict = 其所有条目的最差值。

## 4. 门禁行为（gate）

`finish` 在建 deck **之前**执行门禁：

- 默认模式：**自动丢弃** unverified 条目（bullet / claim / 图 / 证据），
  每条丢弃写入 `change_log`（含 slide 序号、原文、原因），并汇总进
  `fidelity_report.json` 的 `summary.dropped`。清洗后的计划写入
  `slide_plan.verified.json`，deck 只从该计划构建。
- `--strict` 模式：发现任何 unverified 即 gate=fail、退出码非零，并给出
  明确修复指令（改 plan 后重跑 finish）。
- **绝不**静默保留未核验数字上页。

## 5. 为什么丢弃而不是保留

1. 评测与真实科研流程都把"数字与源材料一致"作为硬指标；一个无据数字的
   代价远高于少一条 bullet。
2. 保留未核验内容会让报告表面更丰满、实则不可复核，破坏"逐页核对"的
   可复跑性。
3. 丢弃是可逆的：change_log 记录了原文与原因，Agent 找到真实出处后可在
   下一轮把内容加回并重新过门禁。
4. loose 内容保留但标记，是因为数字确实存在于源文中，只是锚点不够精确
   ——这是可修复的定位问题，不是事实问题。

## 6. 图的字节级溯源

图不只检查"存在"：plan 中的图路径必须与台账 `file` 指向同一文件，或至少
sha256 完全一致；路径不同但字节一致记 `loose`，字节不同（被缩放/转码/
替换）记 `unverified` 并丢弃。构建 deck 时只允许嵌台账图，等比缩放由
pptx 容器完成、不改源文件。

## 7. 已知边界（诚实声明）

- 单位换算（如 0.5 h ↔ 30 min）无法通过逐字核验，会被判 unverified —
  需要 Agent 改写为原文形式。
- 跨页断行的引文可能无法通过逐字子串判定。
- 截图/扫描件 PDF 无文本层时台账为空，门禁会把一切判 unverified —
  此时应记 degraded 并明确说明，而不是绕过门禁。
