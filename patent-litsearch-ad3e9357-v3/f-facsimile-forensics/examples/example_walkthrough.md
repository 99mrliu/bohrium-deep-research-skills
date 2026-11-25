# 示例走查（example_walkthrough.md）

> **合成示例 / 示意输出**：本走查使用的全部材料均为虚构夹具（见各文件头注释），
> 不对应任何真实专利、申请人或数据库记录。下列"预期输出"为节选示意，
> 字节区间等数值以提取文本层为准，poppler 与标准库回退产生的空白可能略有差异。

本走查在技能根目录执行，产物写入 `examples/output/`（用完可整个删除）。

## 夹具说明（examples/fixtures/，全部合成）

- `FX-2099-0123456-A1_frontpage.pdf` — 手工制作的最小合法单页 PDF（未压缩内容流、Helvetica），
  含虚构公开号 `US 2099/0123456 A1`、虚构申请人、申请日，以及一行跨行断裂的 WO 记录。
- `rec_FX1001.txt` — 合成纯文本专利记录，含一条跨 OCR 页边界合并的 WO 记录（已声明保留）。
- `db_FX1001.txt` — 合成数据库式记录，与传真件有**一处刻意差异**：发明人姓氏误拼为 `HOLLOWEY`（传真件为 `HOLLOWAY`）。
- `anchor_policy.json` — 合成容差策略，声明允许空白折叠与跨页合并，并登记 WO 合并边界。
- `case_fixture.json` — 模仿 `/input/case.json` 形态的合成案例（含 `case_id` 与 `output_contract`）。
- `../fields_spec.json` — 合成字段比对规格（4 个字段）。

## 第 1 步：清点与文本层提取

```bash
python3 scripts/facsimile_register.py --input-dir examples/fixtures --out-dir examples/output/register
```

预期输出（示意）：

```
inventory written: examples/output/register/facsimile_inventory.json (5 files, 0 degraded)
```

`facsimile_inventory.json` 中 PDF 条目（示意节选）：

```json
{
  "path": "FX-2099-0123456-A1_frontpage.pdf",
  "sha256": "a64e70fba8d02d5227c31744bd1029db2fb19163f3d9e262ccb3c5a8b628cb5f",
  "size_bytes": 1167,
  "kind": "pdf",
  "extraction": {"method": "poppler-pdftotext", "degraded": false,
                 "pages": [{"page": 1, "char_count": 395}],
                 "pages_file": "extracted/a64e70fb....pages.json"}
}
```

（无 poppler 的环境中 `method` 为 `stdlib-fallback`，字符数可能略有差异；后续步骤不受影响。）

## 第 2 步：定位锚点

```bash
PDFP=examples/output/register/extracted/a64e70fba8d02d5227c31744bd1029db2fb19163f3d9e262ccb3c5a8b628cb5f.pages.json

# 2a. 精确匹配
python3 scripts/page_anchor.py locate --pages "$PDFP" \
  --field publication_number --value "US 2099/0123456 A1" \
  --policy examples/fixtures/anchor_policy.json \
  --out examples/output/anchor_pub.json
```

预期锚点（示意节选）：`page: 1`、`line_span: [3, 3]`、`quote: "US 2099/0123456 A1"`、
`match_type: "exact"`，退出码 0。

```bash
# 2b. 需要已声明容差的匹配（值跨文本层换行）
python3 scripts/page_anchor.py locate --pages "$PDFP" \
  --field related_wo --value "WO 2099/054321 A1 merged across OCR page boundary" \
  --policy examples/fixtures/anchor_policy.json \
  --out examples/output/anchor_wo.json
```

预期：`match_type: "whitespace_collapsed"`，`quote` 为 `"WO 2099/054321 A1\nmerged across OCR page boundary"`
（保留原始换行），`line_span: [8, 9]`，退出码 0。

```bash
# 2c. 反例：同一值但策略未声明容差 -> 拒绝
echo '{}' > examples/output/empty_policy.json
python3 scripts/page_anchor.py locate --pages "$PDFP" \
  --field related_wo --value "WO 2099/054321 A1 merged across OCR page boundary" \
  --policy examples/output/empty_policy.json
```

预期退出码 1，stderr（示意）：

```
REFUSED: value 'related_wo' matches only with whitespace collapsing (e.g. across a line break), but the policy does not declare allow_whitespace_collapse
```

```bash
# 2d. 反例：伪造/不存在的值 -> 拒绝
python3 scripts/page_anchor.py locate --pages "$PDFP" \
  --field publication_number --value "US 2099/9999999 A9"
# 预期退出码 1：NOT FOUND ...

# 2e. 核验锚点真实性
python3 scripts/page_anchor.py verify --pages "$PDFP" --anchor examples/output/anchor_pub.json
# 预期退出码 0：verify OK: 1 anchor(s) check out ...
```

## 第 3 步：传真件 vs 数据库差异台账

```bash
DBP=examples/output/register/extracted/c5e1ee763ffe184786e0fbe424a2ef1854940e37e9af42fafe0f2792a4abd3c0.pages.json
python3 scripts/facsimile_discrepancy.py \
  --spec examples/fields_spec.json \
  --facsimile-pages "$PDFP" --record-pages "$DBP" \
  --policy examples/fixtures/anchor_policy.json \
  --out examples/output/ledger.json
```

预期输出（示意）：

```
ledger written: examples/output/ledger.json (fields=4 consistent=3 discrepancy=1 unanchored=0)
```

台账中 `inventor` 条目（示意节选）：

```json
{"field": "inventor", "status": "discrepancy", "severity": "major",
 "facsimile": {"value": "HOLLOWAY, Priya N.", "anchors": [{"quote": "HOLLOWAY, Priya N.", "page": 1, "match_type": "exact"}]},
 "record":    {"value": "HOLLOWEY, Priya N.", "anchors": [{"quote": "HOLLOWEY, Priya N.", "page": 1, "match_type": "exact"}]}}
```

其余 3 个字段（`publication_number`、`applicant`、`filing_date`）均为 `consistent`。
差异两侧都带锚点，可直接复核。

## 清理

```bash
rm -rf examples/output
```
