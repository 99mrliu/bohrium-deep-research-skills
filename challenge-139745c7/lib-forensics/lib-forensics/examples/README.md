# 合成最小示例（lib-forensics）

**本目录是合成示例，用于说明接口与流程，不是正式案例结果。**

`library/` 内有 4 个合成文件：

| 文件 | 构造的病灶 |
|-|-|
| `实验记录_2023.md` | 正常 Markdown 文本 |
| `实验记录_2023_副本.md` | 与上一份逐字节相同的改名副本 |
| `数据导出_202307.pdf` | 扩展名是 .pdf，内容其实是 UTF-8 文本（type_mismatch） |
| `notes.txt` | 正常文本 |

`case.json` 为合成的最小输入，含 `case_id`、`library_root`、`questions`、
`output_contract`（演示字段：summary / answers / excluded / uncertainty）。

## 运行

```bash
cd examples
python3 run_example.py
```

脚本在本目录下创建 `work/` 与 `output/`，依次执行
`forensics_case.py → forensics_scan.py → forensics_answer.py →
forensics_result.py`（脚本路径自动定位到 `../scripts/`）。

## 预期结果（合成示例的期望行为）

- `work/inventory.json`：`实验记录_2023_副本.md` 状态为 duplicate，
  canonical 指向无别名标记的 `实验记录_2023.md`；
  `数据导出_202307.pdf` 状态为 suspect，issues 含 type_mismatch。
- `work/recovery.jsonl`：至少 2 行（副本去重 + 类型不符标记）。
- `output/result.json`：含 case_id 与 output_contract 全部字段；
  提问"缓冲液配方写在哪份记录"命中 `实验记录_2023.md`；
  excluded 列出副本与 suspect 文件。
