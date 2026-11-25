# 规范化规则目录(Rule Catalog)

`scripts/name_norm.py` 将每条规则实现为独立小函数。**只有当规则真正改变了字符串**,
才在该名称的 `applied_rules[]` 中追加 `{"rule": <id>, "raw": <规则作用前>, "normalized": <规则作用后>}`;
无变化的规则不产生审计条目(例如 `inc` 已是规范形时 R4 不重复记录 no-op)。

## R1 — Unicode NFC + 空白规整

- NFC 规范化;压缩连续空白为单个空格并去除首尾空白。
- 例:`"Acme,\u00a0Inc."`(含不换行空格)→ `"Acme, Inc."`。

## R2 — 大小写折叠(case folding)

- Unicode `casefold()`;拉丁字母全部折叠为小写,CJK 字符不受影响。
- 例:`"ACME INCORPORATED"` → `"acme incorporated"`。

## R3 — 标点剥离(punctuation stripping)

- 所有非字母数字、非空白字符替换为空格,再压缩空白。CJK 字符保留(`isalnum` 为真)。
- 例:`"Acme, Inc."` → `"acme inc"`;`"Co., Ltd."` → `"co ltd"`;`"S.A. de C.V."` → `"sa de cv"`。

## R4 — 法律后缀规范化(legal-suffix canonicalization)

- 数据文件:`references/legal_suffix_table.json`(39 条 canonical 后缀,每条含 `forms` 与 `jurisdiction` 注记)。
- 匹配方式:最长形式优先;每个形式条目至多替换一次;形式不得吞掉整个名称;
  已是规范形的片段不重复替换。匹配发生在 R2/R3 之后,因此表内 `forms` 均按 R3 后的形态书写。
- 例:`"acme incorporated"` → `"acme inc"`;`"globex limited"` → `"globex ltd"`;
  `"acme gmbh co kg"` → `"acme gmbhcokg"`;`"... 株式会社"` → `"... kk"`。
- 已知风险(确定性权衡,非缺陷):`co`/`ab`/`as` 等短形式存在歧义。`as` 仅收录完整形式
  `aksjeselskap`,不收录裸 `as`;`co`/`ab` 保留但要求至少另有一个 token 才会替换,
  且全部转换都在审计轨迹中可见、可回放。

## R5 — 类别判定(kind classification)

输出 `kind ∈ {org, person, unknown}` 及文字依据 `basis`:

1. 存在 canonical 法律后缀 → `org`(依据:后缀名);
2. 含机构关键词(research/lab/university/institute/…) → `org`(依据:关键词);
3. 含 CJK 且 2–4 个 token → `person`(依据:CJK 人名模式);
4. 2–3 个纯字母 token → `person`(依据:拉丁人名模式);
5. 其余 → `unknown`。

## 派生字段

- `tokens`:规范化后的 token 序列;`core_tokens`:剔除 canonical 后缀 token 后的核心序列;`core`:其连接串。
- `canonical_suffix`:命中的 canonical 后缀(无则 `null`);`cjk`:原文是否含 CJK。

## 匹配阶段的安全 flag(scripts/entity_match.py)

- `order_variant`:两侧均为 person、token 多重集相同但语序不同(如 "Zhang Wei" vs "Wei Zhang")。
  **强制 candidate**,即使分数再高也不得 auto。
- `suffix_conflict`:两侧 core 相同但 canonical 后缀不同(如 "Globex Ltd." vs "Globex GmbH")。
  核心名相同而法域后缀冲突,**强制 candidate** 并在记录中保留冲突事实。
