# 对账方法学（claim_audit）

> 本文件是 provenance-ledger-gate 的规范性说明。示例数据均为合成示例 / SYNTHETIC EXAMPLE。

## 1. 六种 verdict

| verdict | 含义 | 是否缺陷（阻断比较） |
|---|---|---|
| `supported` | given/conflict 断言的 quote 在来源文本中逐字命中，且 value 数值与 quote 数值不矛盾 | 否 |
| `unsupported` | quote 在来源文本中找不到；或来源文件无可用抽取文本（needs_extraction）；或 status 非法 | **是** |
| `conflict` | quote 命中，但 value 中的数值与 quote 中的数值无交集（如 quote 写 10% 而 value 写 12） | **是** |
| `missing_source` | given/conflict 断言缺少 source.file/source.quote，或 source.file 未登记于 registry | **是** |
| `recorded_inferred` | 输入 status=inferred：模型推断值，只记录不判负；进入比较时必须标注为假设 | 否 |
| `recorded_missing` | 输入 status=missing：方案未给出该字段，记录为缺口 | 否 |

任一 `unsupported` / `conflict` / `missing_source` → claim_audit 退出码 3，
stdout 打印 `DEFECT\t<verdict>\t<plan_id>\t<field_group>.<field>\t<detail>` 缺陷清单；
audit.json / audit.md 无论是否拦截都会写出（能写的产物仍写出）。

## 2. 规范化规则

- 对 quote 与来源全文分别做 **NFKC 规范化**（`unicodedata.normalize("NFKC", s)`），
  消除全角/半角、兼容字符差异（如 ℃ → °C、全角数字 → ASCII 数字）。
- 再把所有空白串（含换行、制表符）**折叠为单个空格**并去首尾空白。
- 在规范化后的来源全文中 `find()` 规范化后的 quote；命中位置记为 `char_offset`
  （相对规范化文本的字符偏移，便于人工复核）。
- 数值矛盾判定：分别用正则 `-?\d+(\.\d+)?` 抽取 value 与 quote 中的数值集合；
  若两者均非空且**无交集** → conflict；其余情况（一方无数值）不做数值判负，
  quote 命中即 supported。

## 3. locator 写法

locator 是人读定位信息，不参与机检，但必须可复核，格式：`file 内位置`：
- 文本/PDF 抽取文本：`第N页 第M段`、`第N页 表K 第R行`、`Section X.Y`；
- 契约/清单：`条目 N`、`条款 N`、`表头"单价"列 第R行`；
- JSON/结构化材料：`键路径，如 items[2].unit_price`。

quote 才是机检锚点：必须是来源文本的**逐字片段**，长度建议 10–60 字，
须包含支撑 value 的关键数字/实体；禁止改写、翻译、拼接（跨段拼接必失配）。

## 4. 输入 status 与核验范围

- `given`：方案或来源明示的事实断言 → 必须核验（四种结果之一）。
- `conflict`（输入态）：方案内部或两来源之间已被模型发现互相矛盾的断言 →
  与 given 同样核验；核验通过记 supported，矛盾在 detail 中保留说明。
- `inferred` / `missing`：只登记，不判负，但必须在 result.json 的
  uncertainty / confirmations 中显式体现，不得写成已确认事实。

## 5. 隔离原则

被判缺陷的论断所属字段**整字段隔离**：该方案的该字段不得进入比较表与最终选择；
若某方案关键字段（参数、资源）被隔离到无法比较，则在 result.json 中记录
"该方案不可比/不可行"及原因，而不是补一个无来源的数字。
