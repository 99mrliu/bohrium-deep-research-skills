# examples/ — 合成示例 SYNTHETIC EXAMPLE

本目录全部为**合成示例**：case_id 为 `synthetic-demo-001`，
`source_excerpt.txt` 中的电池/材料数据系虚构，仅用于演示本技能的
契约化填充、真实渲染预览与门禁交付流程。**不含任何隐藏案例的预制答案。**

## 文件

| 文件 | 说明 |
| --- | --- |
| `case.json` | output_contract 为 list-of-obj 形态，4 个必填字段：answer_summary(string)、item_bank(array)、evidence_map(object)、status_note(string) |
| `task.md` | T2 出题工单：从 source_excerpt.txt 起草 2 道题卡（正式工单为 4 道） |
| `source_excerpt.txt` | 虚构的固态电解质段落 + 退火温度/电导率小表格（共 14 行） |
| `items.json` | 预制的 agent 工作文件：item_bank（2 道题卡）+ answer_summary + status_note |
| `evidence_map.json` | 证据锚点映射，锚点指向 source_excerpt.txt 真实行号（L5、L7、L13 等） |
| `run_example.sh` | 端到端演示：先以缺字段变体演示 BLOCK，再补全演示 DELIVER |

## 运行

```bash
bash run_example.sh /tmp/a1d81ca4-b-demo-out   # 参数为输出目录，默认 ./out
```

缺字段变体（移除 `item_bank` 的 items.json）由脚本在运行时就地生成，
不作为独立文件携带。

## 预期产物（`$OUT/output/`）

- `result.json`：含 case_id、4 个契约字段、status、status_reason、sources、
  uncertainty、change_records、field_provenance。ROUND1 为"部分完成"
  （item_bank=null）；ROUND2 为"成功"。
- `preview.svg`：可编辑 SVG 状态面板（xml.etree 校验 well-formed）。
- `preview.png`：内置 stdlib PNG 编码器栅格化的真实位图（`file` 应识别为
  `PNG image data`）。
- `preview_hd.png`（可选）：系统存在 rsvg-convert/inkscape/magick 时生成。
- `preview_record.json`：各产物 sha256 与渲染器信息。
- `gate_report.json`：ROUND1 verdict=BLOCK（null 字段：item_bank）；
  ROUND2 verdict=DELIVER。

## PNG/SVG 预览目检要点

1. 顶部深蓝标题条文字为 `CONTRACT-RENDER-GATE PREVIEW`。
2. `FIELDS: REQUIRED FILLED` 计数：ROUND1 显示 3/4，ROUND2 显示 4/4。
3. 字段矩阵每行左侧色块：绿色=已填充，红色=必填但为 null（ROUND1 的
   `item_bank` 行应为红色，ROUND2 全部转绿）。
4. ITEMS 区每道题一行，右侧蓝色条形长度与证据锚点数成正比
   （item_1 为 2 个锚点、item_2 为 1 个锚点，条长比例 2:1）。
5. 内置 PNG 使用 5x7 ASCII 点阵字体，不渲染 CJK；中文内容在 PNG 中
   显示为 `?`，属预期行为（CJK 请查看 SVG 版本）。
