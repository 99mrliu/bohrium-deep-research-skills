# 日期文法与歧义规则（date_norm.py 所支持的格式）

本文件列出 `scripts/date_norm.py` 正则文法表支持的全部格式、对应的 `format_tag`、精度标志，
以及歧义与 OCR 处理规则。未命中任何文法的字符串一律“保留原文 + 警告”，绝不猜测。

## 支持的格式

| format_tag | 形态 | 示例 | 精度 |
| --- | --- | --- | --- |
| `iso8601` | YYYY-MM-DD | `2018-06-05` | day |
| `iso8601_month` | YYYY-MM | `2018-06` | month |
| `year_only` | YYYY（1800–2199） | `2018` | year |
| `zh_ymd` | YYYY年M月D日 | `2018年6月5日` | day |
| `zh_ym` | YYYY年M月 | `2018年6月` | month |
| `us_long` | 月名 D, YYYY（月名可缩写带点，可带 st/nd/rd/th） | `Jun. 5, 2018`、`June 5, 2018` | day |
| `eu_long` | D 月名 YYYY | `5 June 2018` | day |
| `numeric_slash_us_mdy` / `numeric_slash_eu_dmy` | M/D/YYYY 或 D/M/YYYY | `6/5/2018` | day |
| `numeric_dot_dmy` / `numeric_dot_mdy` | D.M.YYYY 或 M.D.YYYY | `5.6.2018` | day |
| `compact_yyyymmdd` | YYYYMMDD | `20180605` | day |
| `ocr_fixed:<tag>` | 上述任一格式经声明的 OCR 数字混淆修复后命中 | `2O18-06-05` → `2018-06-05` | 同原格式 |

月名支持英文全写与常见缩写（Jan/January … Dec/December，Sept 亦可）。

## 歧义规则（绝不静默取舍）

1. **两段均 ≤12** 的纯数字日期（如 `03/04/2018`）：无法从字符串本身判定美式还是欧式。
   输出 `interpretations` 同时包含两种解释，附 `AMBIGUOUS_NUMERIC_DATE` 警告；
   顶层 `format_tag` 变为 `ambiguous:...`。斜杠格式按 US 在前、EU 在后的顺序罗列
   （仅表示排列顺序，不表示采信）；点分格式相反。
2. **仅一种解释合法**（如 `13/04/2018` 只能是 D/M）：按唯一合法解释归一化，
   附 `NUMERIC_DATE_DISAMBIGUATED` 警告，仍建议人工复核。
3. **两种解释均非法**（如 `15/13/2018`）：视为无法解析，保留原文 + 警告。
4. 下游 `timeline_build.py` 对歧义事件按首个解释排序，但保留全部解释并附
   `AMBIGUOUS_EVENT_ORDERED_BY_PRIMARY` 警告。

## OCR 数字混淆规则

- 默认策略 `keep-raw`：疑似混淆字符串（如 `2O18-06-05`、`2O2O-O6-15`）不解析，
  保留原文，附 `UNPARSEABLE_DATE_KEPT_RAW` 与 `SUSPECTED_OCR_DIGIT_CONFUSION` 警告。
- 显式策略 `--ocr-policy fix-digit-confusion`：仅在用户确证来源为 OCR 扫描件时启用。
  映射表：O/o/Q→0，l/I/|→1，Z→2，S/s→5，G/b→6，B→8，g/q→9。
  修复成功则 `format_tag` 加前缀 `ocr_fixed:`，附 `OCR_DIGIT_CONFUSION_FIXED` 警告；
  **该修复仅为工作假设，必须人工核对原件**；修复失败仍按 keep-raw 处理。
- 修复映射只用于解析，不改写输出中的 `raw` 与 `quote`（始终为逐字原文）。

## 文本扫描（event_extract 定位规则）

- 扫描正则与锚定文法一一对应，另有兜底的 `ocr_suspect` 文法识别含混淆字符的日期形。
- 重叠匹配按“起点优先、同起点长者优先、文法表顺序优先”去重
  （例如 `2018-06-05` 内的 `2018` 不会重复产生事件）。
- 解析失败的普通候选直接丢弃（避免把编号片段如 `SYN-PUB-0001` 中的 `0001` 误报为事件）；
  仅 `ocr_suspect` 候选在失败时仍保留（原文 + 警告），以便人工发现 OCR 错乱日期。
- 年份口径要求 1800–2199，且不得与字母/数字紧邻（`CN2018`、`GX1001` 中的片段不计）。
