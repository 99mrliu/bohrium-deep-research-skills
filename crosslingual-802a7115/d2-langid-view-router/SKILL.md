---
name: xlang-langid-view-router
description: 跨语言文献检索的语言识别与视图路由（language identification & view routing）。对候选记录用真实正文判定语种（停用词画像、变音字符签名、CJK/假名计数，附置信度与可复核证据，绝不盲信 language 标签），把同一工作的多个语种记录聚成 work，并将每个视图分类为 original / translation / bilingual / abstract_only / duplicate，输出逐视图的查询语言路由与去重计数规则。当任务要求"每条命中说清来自哪个语种和哪个版本"、同文多语版本需要去重计数、或输入混有出版方全译本/仅摘要记录/完全重复副本时使用；适用于 /input/case.json + task.md 的 Harbor 运行契约。
---

# 语言识别与视图路由（xlang-langid-view-router）

## 用途与适用条件

跨语言检索中"命中的论文究竟是原文还是译文、同一篇是否被多语种重复计入"是指标虚高的主因。本 Skill 的重心是**用正文证据判定语种、把记录归并成 work、给每个视图定类与计数规则**，让下游检索/排序/计数都建立在可靠的语种与版本判断上。

不做：术语翻译、相关性排序、全文内容复核。视图分类只依赖可复核证据（DOI、标题相似度、正文长度、显式翻译标记、文本重复度），不臆断。

## 运行契约

- 输入：`/input/case.json`（含 `case_id`、`output_contract`）、`/input/task.md`、候选记录文件（JSON/JSONL/CSV/TSV/TXT/MD/PDF，可能在 `/input` 任意子目录）。
- 工作目录 `/app/work`；最终交付 `/app/output/result.json`，含 `case_id` 与 `output_contract` 全部字段的镜像；诚实 `status`、`sources`、`uncertainty`。
- PDF 用平台 `pdftotext` 真实抽取；抽取失败记入 parse_notes，不伪造正文。

## 调用方式

```bash
# 1. 语种判定 + work 聚类 + 视图分类 + 路由表
python3 scripts/langid_views.py --roots /input /app/work \
    --out /app/work/langid --exclude examples

# 2. 人工抽查 /app/work/langid/routing_report.md：
#    每个 work 的成员、视图分类与证据是否成立；置信度 <0.7 的记录逐条复核。

# 3. 下游按 routing 使用：
#    - query_languages：该 work 需要覆盖的查询语种集合；
#    - countable=no 的视图（duplicate）只保留归因、不计入命中数；
#    - abstract_only 视图不得当作全文证据，仅能支持"存在性"结论；
#    - result.json 的每条命中照抄 detected_language 与 view_type 及其证据。
```

完全离线、仅标准库；数秒内完成，不消耗模型请求。

## 输出

`/app/work/langid/`：

- `views.json`：`works[]`（work_id、doi、title、members[]，成员含 declared/detected 语种、置信度、证据、view_type、view_evidence、declared_type 对照）、`routing[]`（逐视图 query_languages / countable / count_note / evidence）、`parse_notes`。
- `routing_report.md`：人读的 work 分组表 + 路由表。

## 关键方法（详见 references/langid_policy.md）

1. **语种判定**：正文优先。假名≥5→ja，汉字≥10→zh；拉丁语系按停用词命中数＋变音字符画像（ã/õ/ç→pt、ñ→es、ä/ö/ü/ß→de）打分，置信度由前两名分差决定，全部得分留档。
2. **work 聚类**：DOI 相同或规范化标题 token Jaccard ≥ 0.6 归为一 work。
3. **视图分类优先级**：duplicate（同语种正文 Jaccard≥0.9）→ translation（显式翻译标记，如 "Translated from"/"Versão em português"）→ abstract_only（无全文但有摘要，body<1500 字符）→ translation（同 work 异语种、无标记）→ bilingual_or_undetermined → original。每步都写证据字符串。
4. **路由与计数**：work 内全部已判语种构成该 work 的查询语种集合；duplicate 视图 countable=no；多视图 work 一律"每 work 计一次"。
5. **诚实性**：declared_language/declared_type 与判定冲突时两者都保留并写 `view_note`；语种不定（und）的记录不计入任何语种覆盖，写入 uncertainty。

## 异常处理

| 情况 | 处置 |
|-|-|
| 文本过短/无拉丁 token | detected=und，conf=0，报告注明原因；不计入语种覆盖 |
| 标签与正文冲突 | 以正文为准，标签保留对照并写 view_note |
| 只有摘要无全文 | view=abstract_only；result.json 中禁止当作全文证据 |
| 同 work 异语种但无翻译标记 | 仍分类为 translation，证据明确写"无显式标记，依据聚类与语种差" |
| PDF 抽取失败 | body_chars=0，按 abstract_only 或 und 处理，parse_notes 记录 |
| 根目录不存在 | 记 parse_notes 继续；全部缺失时 views.json 仍生成（空 works） |

## 自查方法

1. 每个 work 的每个成员都有 view_type 与 view_evidence，证据能回指正文/DOI/标题；
2. 置信度 <0.7 的语种判定已人工复核（对照 lang_evidence 的各语种得分）；
3. 路由表中 duplicate 视图 countable=no，多视图 work 计数规则一致；
4. result.json 中每条命中的语种/版本字段与本脚本输出逐字一致，无推断字段。

## 最小调用示例

见 `examples/example_walkthrough.md`（**合成示例**，非正式案例结果）。
