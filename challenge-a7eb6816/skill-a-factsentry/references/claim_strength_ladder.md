# 论断强度分级表（Claim Strength Ladder）

本表是 `scripts/ledger_extract.py` / `scripts/fact_check.py` 内置强度词表的说明文档，
两者必须保持一致。用途：检测改写稿相对源文的**论断强度升格**（strength_upgrade）。

## 分级（0 → 4 单调增强）

| 级别 | 名称 | 中文动词/措辞 | 英文动词/措辞 | 语义 |
| --- | --- | --- | --- | --- |
| 0 | 推测 hedge | 可能、或许、有望 | may、might、could、possibly | 不确定的猜测或前景 |
| 1 | 提示/初步 tentative | 提示、初步表明、初步显示 | suggests、indicates、hints、preliminarily shows | 有限证据下的初步指向 |
| 1.5 | 相关 correlation | 相关、关联 | correlates (with)、(is) associated (with)、linked | 共变关系，**不含因果** |
| 2 | 表明 show | 表明、显示 | shows、reveals | 数据直接支持的陈述 |
| 2.5 | 实证 demonstrate | —（中文常以「实验表明」表达，归入 2 或 3 需人工裁决） | demonstrates | 经实验/分析实证 |
| 3 | 证实 confirm | 证实、证明、确证 | confirms、proves | 确证性结论，强度最高等级的非因果表述 |
| 4 | 因果断言 causal | 导致、致使、治愈、根治、消除 | causes、cures、eliminates、eradicates | 因果/疗效断言，需要干预性证据支撑 |

## 判定规则

1. **同句取最高**：一个句子含多个强度词时，该句强度取最高级别
   （例：「…表明…，但…仍可能…」按 2 计）。
2. **升格判定**：改写稿句子与源文句子按锚句相似度配对后，
   `改写稿级别 > 源文级别` 即记 strength_upgrade（mandatory）。
   同级替换（表明→显示、可能→或许）不告警。
3. **相关 → 因果**：因果断言为最高级 4。源文为「相关/关联/correlates」（1.5）而
   改写稿出现「导致/治愈/根治/causes」时必然触发告警——
   除非源文同一锚句本身含因果词（即有干预证据的直接表述）。
4. **降级不告警**：改写稿弱化论断（证实→提示）不违反保真，不记发现
   （但过度弱化改变结论含义时应由人工复核）。
5. **中英混排**：中文词按子串匹配（最长优先，避免「初步表明」中的「表明」重复计数）；
   英文词按词干+词形变化匹配（demonstrate/demonstrates/demonstrated），
   带词边界（because 不命中 cause，maybe 不命中 may）。

## 常见升格模式（改写高频错误）

| 源文 | 改写稿 | 判定 |
| --- | --- | --- |
| 初步表明 X 促进 Y | 证实了 X 促进 Y | 升格 1→3 |
| 活性与浓度相关 | 浓度升高导致活性提升 | 升格 1.5→4（相关→因果） |
| may improve | demonstrates | 升格 0→2.5 |
| 结果显示 A 优于 B | 结果证明 A 优于 B | 升格 2→3 |
| 有望用于临床 | 可治愈 / 将治愈 | 升格 0→4 |
| 表明 | 显示 | 同级，不告警 |
