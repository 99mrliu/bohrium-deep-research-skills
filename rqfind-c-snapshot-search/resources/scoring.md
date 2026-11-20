# 索引与打分说明（可复算）

## 分词

- 拉丁：NFKC 规范化 → 小写 → 保守截尾（s/es/ies/ed/ing/edly/ingly）→ 去停用词（resources 内常量）。
- CJK：连续中文字符取二元组（如"晶界钝化"→ 晶界,界钝,钝化）。
- 字段权重：title 3.0、keywords 2.0、abstract 1.0、authors/venue 0.5。

## 打分

score(doc, q) = Σ_t [Σ_fields tf·field_weight(t)] · log(1 + N/df_t)

- 前缀 `+`：必须命中（AND）；前缀 `-`：排除（NOT）；无符号：OR 加权；引号：短语整体分词。
- `--query-zh` 的中文二元组命中额外 ×2.0（弥补拉丁分词对中文的欠召回）。
- 年份窗与 exclude-type 是**硬过滤**，不进打分。
- 每条候选输出 `matched_terms`（按字段列出命中词与权重）与 `origin`（文件!行号），任何人可用 docstats.json 的 df 值复算 score。

## 扩展预算

expand.py 每词最多 max-variants 个变体；词表命中优先，规则次之；未命中不扩展。防止"同义词爆炸"把查询发散到无关主题——这是受控扩展的核心约束。
