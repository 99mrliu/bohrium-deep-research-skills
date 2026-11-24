# OCR 容差声明规则（Tolerance Declaration）

默认状态下，审计只接受**逐字（空白归一化后的精确子串）**匹配。容差模式是为
OCR/扫描件噪声保留的唯一例外，且必须满足**双重声明**，缺一不可。

## 1. 何时允许

仅当源文件本身是 OCR 产物或传真/扫描转写文本、存在可预期的字符级噪声
（典型：`0`↔`O`、`1`↔`l`↔`I`、`5`↔`S`、`8`↔`B`、随机空格）时，才允许容差匹配。
对原生数字文本（数据库导出、XML、HTML）一律不得使用容差。

## 2. 如何声明（双重声明）

**第一重：登记时预声明（源文件级）**

```bash
python3 $S/source_register.py --roots /input --out /app/work/registry.json \
    --tolerance-ocr /input/uspto_fax_ocr.txt
```

登记表中该文件条目携带 `"tolerance": "ocr"`。

**第二重：锚点级声明**

```json
{
  "field": "candidates[0].publication_number",
  "quote": "公开号：USO000000EX1",
  "source_path": "/input/src_patent_EX1001.txt",
  "source_sha256": "<sha256>",
  "tolerance_used": true
}
```

## 3. 判定方式

容差判定时，审计器在归一化后的源文本中滑动窗口，计算 quote 与各候选窗口的
**带限编辑距离**，上限为 `max(2, len(quote) // 20)`：存在距离不超上限的窗口即 PASS，
并在汇总中计入"声明式容差"。超出上限仍 FAIL。源文本超过 200,000 字符时不执行
容差搜索并 FAIL（防止在大文件上退化为模糊匹配）。

## 4. 反例（一律 FAIL，exit 1）

- quote 有 OCR 噪声、源文件已预声明 `tolerance: "ocr"`，但锚点缺少
  `tolerance_used: true` → FAIL（undeclared tolerance）；
- 锚点写了 `tolerance_used: true`，但登记时未对该文件 `--tolerance-ocr`
  → FAIL（undeclared tolerance）；
- 借容差之名改写、补全、翻译文本 → 距离超限或语义不符，FAIL。

## 5. 记录义务

每个使用容差的锚点，必须在 `uncertainty` 中追加一条说明：源文件、原 OCR 片段、
采信的解读、以及编辑距离量级。容差锚点过多的 result 应降为 `partial` 并说明原因。
