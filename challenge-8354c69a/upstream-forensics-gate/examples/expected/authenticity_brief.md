# 上游数据真实性取证简报

- 文件数: 5
- 门禁结论: **PASS_WITH_FLAGS**

## 取证发现（按严重度）

- [high] identical_files: `[["demo/input/batch_a.csv", "demo/input/batch_a_copy.csv"]]`
- [medium] saturation_suspects: `{"file": "demo/input/batch_a.csv", "saturation_suspects": [{"col": 2, "longest_identical_run": 30, "value": 1.0}]}`
- [medium] constant_columns: `{"file": "demo/input/batch_a.csv", "constant_columns": [2]}`
- [medium] saturation_suspects: `{"file": "demo/input/batch_a_copy.csv", "saturation_suspects": [{"col": 2, "longest_identical_run": 30, "value": 1.0}]}`
- [medium] constant_columns: `{"file": "demo/input/batch_a_copy.csv", "constant_columns": [2]}`
- [medium] duplicate_data_rows: `{"file": "demo/input/batch_b.csv", "duplicate_data_rows": 2}`
- [medium] saturation_suspects: `{"file": "demo/input/batch_b.csv", "saturation_suspects": [{"col": 1, "longest_identical_run": 8, "value": null}, {"col": 2, "longest_identical_run": 30, "value": 7.0}]}`
- [medium] constant_columns: `{"file": "demo/input/batch_b.csv", "constant_columns": [2]}`
- [medium] unit_ambiguity: `{"浓度": ["mg/mL", "ug/mL"]}`
- [high] cross_file_overlap: `[["demo/input/batch_a.csv", "demo/input/batch_a_copy.csv"]]`

## 阈值声明
- F1: 文件全文 sha256 相同判为完全重复
- F2/F3/F4: {"duplicate_row": "数据行完全相同(全部数值列)", "saturation": "同列相同读数连续段>=5", "constant": "列内取值唯一(方差为0)"}
- F5: 同一物理量关键词在一行内/跨行对应多个不同单位记号即登记歧义
- F6: 两文件数值集合(6位小数)完全一致
- F7: state!=visible 的 sheet 记为隐藏 sheet 需人工确认
- F8: 脚本引用文件名须与 /input 实际文件一一对应
