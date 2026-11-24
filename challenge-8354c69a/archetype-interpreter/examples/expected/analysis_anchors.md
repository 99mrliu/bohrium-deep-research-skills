# 分析锚点（合成示例/真实运行均由脚本生成，可直接引用）

- 识别原型: `bending_traces`
- 识别证据: `{"n_files": 42, "by_ext": {".json": 1, ".md": 1, ".txt": 40}, "two_col_traces>=20pts": 40, "has_matlab": false, "has_pdf": false, "xlsx_sheets_max": 0, "keywords": {"bending": true, "iris": false, "cefixime": false}, "archetype": "bending_traces"}`

## 弯曲 traces
- trace 数: 40
- 峰值 mean±std: 818.3994 ± 139.3100 (min=721.3140, max=1410.4520)
- IQR 离群 traces: ['trace_005.txt', 'trace_013.txt', 'trace_027.txt']
- 饱和 traces(平台≥5): ['trace_005.txt']
- 重复曲线组: [['trace_030.txt', 'trace_031.txt']]
- 判定阈值: {"outlier": "峰值 IQR×1.5 (Tukey)", "saturation": "相同读数连续段>=5", "duplicate": "文件内容 sha256 完全相同"}
