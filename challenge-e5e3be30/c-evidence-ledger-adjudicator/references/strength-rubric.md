# 证据强度与极性标注规范（strength-rubric.md）

模型在取证阶段对每条证据标注三个维度：**强度档 strength**、**极性 polarity**、
**锚点覆盖 covers**。标注只描述证据，不决定判定——判定由
`scripts/verdict_engine.py` 按 `references/verdict-rules.md` 从台账算出。

## 1. 强度档 strength（三档）

### direct（直接证据）
证据句/表行**直接报告论断所涉的同一对象、同一结局、同一干预/暴露**，
其数值或方向表述可以逐字引用并逐锚点对应。

- 例（论断："……空腹血糖显著降低"）：结果表行
  "空腹血糖变化：治疗组 −1.8 mmol/L，安慰剂组 −0.2 mmol/L（p=0.003）" → direct。
- direct 证据的 `covers` **不允许为空**（validate W1 会警告）。

### indirect（间接证据）
与论断相关但需要**一步推理**才能连上：替代/代理终点、亚组结果、机制性结果、
相邻人群或相邻干预的结果、定性趋势但缺统计或缺数值。

- 例（论断："HbA1c 降低 30%"）：正文仅写"HbA1c 呈下降趋势，差异无统计学意义"
  → indirect（方向信息有，数值锚点与统计锚点未落实）。

### topical（主题相关，不构成支持）
仅在主题上沾边：引言/背景中的流行病学陈述、文献回顾、
"未评估该结局"的限制声明、与本论断结局无关的结果。

- 例（论断："……改善睡眠质量"）：引言"睡眠质量等患者报告结局日益受到关注"
  → topical。
- **topical ≠ 支持**：若 topical 证据的 covers 标满全部锚点，validate W2
  会警告"疑似把主题相关当作直接证据"；verdict_engine R6 会把
  "只有 topical" 的论断压回 insufficient_evidence。

## 2. 极性 polarity

- **same**：证据所述方向/数值与论断一致。
- **opposite**：证据与论断在方向或数值锚点上矛盾。典型情形：
  - 论断"对 ALT 无影响"，证据"ALT 较基线升高 15%（p=0.02）" → opposite；
  - 论断"HbA1c 降低 30%"，证据"HbA1c 较基线变化 −8%" → 数值锚点上 opposite。
- side 与 polarity 应一致（pro↔same，con↔opposite）；不一致时 validate W5
  警告，裁决只按规则定义的组合（pro+same / con+opposite）取数。

## 3. 锚点覆盖 covers 的判定

covers 列出该证据**实际覆盖**的锚点 id（anchors 由 ledger_init.py 预提取，
模型可增删锚点但须在 change_records 说明）：

- **number**：证据给出可比较的数值（任一变体即可：30% / 0.3 /
  thirty percent / 百分之三十 等价）。
- **comparator**：证据含同向或反向的比较表述（覆盖该锚点，方向由 polarity
  另行表达；反义对如 提升↔降低 视为覆盖同一锚点）。
- **negation**：证据正面触及"无 X"这一主张本身（确认无 X → same；
  报告存在/升高 X → opposite）。
- **condition**：证据来源的人群/条件与论断条件短语一致（如试验对象即
  "2 型糖尿病成人"）。论文整体人群描述可用于覆盖该锚点。
- **causal / quantifier**：证据含对应的因果表述或范围量词。
- **未报告 ≠ 反驳**：证据没提某锚点 ≠ opposite；只有在该锚点上给出
  相反信息才是 opposite。

## 4. quote / page / section 规范

- `quote`：论文**逐字原文**（中英文均可，禁止改写、禁止省略关键数字；
  可用 "…" 拼接同段不相邻的两处，但不得跨段拼接）。
- `page`：PDF 页码（整数）；纯文本来源用 null 并在 section 注明行号范围。
- `section`：章节名 + 表/图号（如 "3 结果 / 表 1"）。
