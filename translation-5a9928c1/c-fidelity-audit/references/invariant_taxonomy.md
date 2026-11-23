# 不变量分类法（invariant taxonomy）

不变量只从 **source 侧** 挖掘；全部检查为确定性字符串/正则匹配，无模型参与。
实现见 `scripts/extract_invariants.py` 顶部常量，两处脚本共用同一词典。

## 1. 数字 numbers
- 正则：`(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)` 后跟可选科学计数 `(?:×|x)\s*10\^?-?\d+|[eE][+-]?\d+` 与可选单位。
- 输出：`{"raw","value","unit"}`，`value` 为去掉千分位的字符串；科学计数存在时附 `sci_exp` 整数。
- 归一化规则：`u→μ`（含 `µ→μ`）、`℃→°C`、去空格、`,` 千分位可剥离；同时保留字符串与 float 两种形态比对（`"92"` vs `"92.0"` 视为同一值）。
- 已知误报与缓解：
  - 年份（如 `2020`）与图号后数字：不连单位的纯数字只要求“出现在译文任意处”，跨段语义错位不由本检查覆盖，交人工。
  - 千分位/空格格式差异 → 记 `number-format` WARNING 而非 BLOCKER（可见即不误报为 lost）。
  - 数字出现在图片（图/表截图）中 → 抽取不可得，整条记 `unable_to_determine`，绝不静默通过。

## 2. 引文 citations
- 正则：`\[(\d+(?:\s*[-,]\s*\d+)*)\]`（`[12]`、`[3,4]`、`[5-9]`）与 `\(([A-Z][A-Za-z\-']+(?:\s+(?:et\s+al\.?|and\s+[A-Z][A-Za-z\-']+))?,\s*\d{4}[a-z]?)\)`（`(Surname, 2020)` 式）。
- 归一化：内部空白压缩，`[3, 4]` 与 `[3,4]` 等价。
- 判据：多重集（multiset）相等；缺失项 → `citation-lost` BLOCKER。译文多出的引文不计错误（保守，交人工）。
- 已知误报与缓解：区间被展开或合并（`[5-9]` vs 文内逐条 `[5][6]…`）会导致多重集不等；当前按缺失计 BLOCKER，若人工确认只是区间写法差异可关闭。参考文献列表段（≥3 个引文标记）会被识别，不参与否定/语气检查。

## 3. 图表/公式引用 refs
- 正则：`(Fig(?:ure)?s?\.?|Tables?|图|表|Eq(?:uation)?s?\.?|式)\s*[（(]?\d+(?:\s*[-–,]\s*\d+)*[）)]?`
- 归一化：类别桶 `Fig.`（含 Figure/图）、`Table`（含 表）、`Eq.`（含 Equation/式），编号空白压缩。
- 判据：多重集相等；缺失 → `ref-lost` BLOCKER。
- 已知误报与缓解：`图 2a` 这类带字母子图的编号会把字母漏掉；缓解：当前只匹配纯数字编号，字母子图差异由人工队列确认。

## 4. 否定 cues
- 词边界正则（source 英文侧）：`\b(?:no|not|never|without|cannot|can't|fails?\s+to|failed\s+to|neither|nor|none|unable)\b`（不区分大小写）。
- 判据：源段含 ≥1 个否定提示词 → 译文必须含 `不|未|无|非|否|无法|不能|没有|缺乏` 之一，否则 `negation-lost` BLOCKER。
- 已知误报与缓解：`no`、`not` 可能出现在否定式地名/固定搭配（如 "North" 不会误中，因词边界）；参考文献列表段（≥3 引文标记）整体跳过本检查，避免 "[12] found no…" 类句式误报。

## 5. 模糊 / 转折 hedges
- 词边界正则：`\b(?:however|although|though|whereas|while|may|might|could|approximately|about|around|up\s+to|at\s+most|at\s+least|only)\b`
- 判据：源段含 ≥1 个提示词 → 译文应含 `可能|或许|大约|约|至多|至少|仅|然而|尽管|虽然` 之一，否则 `hedge-lost` WARNING。
- 已知误报与缓解：`may` 与情态、`while` 与对比均可直译为中文但提示词被意译（如“但”“仅”不在白名单）→ 记 WARNING 交由人工确认；`about` 作“关于”讲会误中，需人工在队列中关闭。
