# examples/ — 合成示例（非正式案例结果）

> **合成示例，非正式案例结果。** `case.json` 与 `manuscript.md` 均为人工构造的
> 演示输入（推介书中的数据、单位、专利数量全部虚构）；`expected/` 是用本技能
> 脚本在本目录下**真实运行**得到的输出，用于演示流水线与回归对比，与平台正式
> 评测案例无关。

## 输入

- `case.json`：合成案例，`output_contract` 为嵌套 JSON-Schema 形态，10 个
  字段（string / integer / number / boolean / array / enum），9 个必填；
- `manuscript.md`：合成成果转化推介书（约 54 行，含标题、加粗、无序/有序
  列表、表格、引用）。

## 真实运行命令与结果

以下命令在 `examples/` 目录下执行（`$SK` = bundle 根目录），运行环境
Python 3.12（仅用标准库）：

### 第 0 步：契约抽取与保底脚手架

```bash
python3 ../scripts/contract_scaffold.py --case case.json --outdir expected/
# 输出：contract_map: expected/contract_map.json（10 个字段，形态=json_schema）
# 输出：scaffold:     expected/result.json
# 退出码：0
```

### 第 2 步：渲染可检查预览

```bash
python3 ../scripts/preview_render.py --md manuscript.md --outdir expected/ --lines-per-page 40
# 输出：preview.html（3857 字节）、preview_page1.svg、preview_page2.svg
# 输出：校验通过：7 个标题均在产物中，产物非空。
# 退出码：0
```

### 第 3 步：回填

用一段 Python 标准库脚本从 `expected/result.json`（脚手架）出发回填真实内容
（word_count=814 由程序实测，非手填），写出 `expected/result_final.json`，
`status=complete`、`limitations=[]`。

### 第 4 步：验收门（正向）

```bash
python3 ../scripts/deliverable_gate.py --case case.json \
  --contract-map expected/contract_map.json \
  --result expected/result_final.json --base-dir expected --outdir expected
# 输出：gate=PASS exit=0 检查 34 项，失败 0 项
# 退出码：0
```

### 负向测试（验收门必须 FAIL）

构造 `expected/result_corrupted.json`：删掉必填字段 `title`、把布尔
`reviewed` 写成 `1`、向 `deliverables` 追加不存在路径
`nonexistent/ghost_preview.html`，然后：

```bash
python3 ../scripts/deliverable_gate.py --case case.json \
  --contract-map expected/contract_map.json \
  --result expected/result_corrupted.json --base-dir expected \
  --report-json expected/gate_report_fail.json --report-md expected/gate_report_fail.md
# 输出：gate=FAIL exit=5 检查 33 项，失败 3 项
#   FAIL: field_present:title — 字段缺失（契约要求必填，类型 string）
#   FAIL: field_type:reviewed — 期望类型 boolean，实际 int（值 1……）
#   FAIL: artifact_exists:deliverables=nonexistent/ghost_preview.html — 路径不存在
# 退出码：5
```

## expected/ 文件说明

| 文件 | 来源 |
|---|---|
| `contract_map.json` | 第 0 步 scaffold 输出（契约字段映射） |
| `result.json` | 第 0 步保底脚手架（status=partial，占位值） |
| `preview.html` | 第 2 步渲染输出（自包含 HTML） |
| `preview_page1.svg` / `preview_page2.svg` | 第 2 步渲染输出（分页文本预览，每页 40 行） |
| `result_final.json` | 第 3 步回填后的最终结果 |
| `gate_report.json` / `gate_report.md` | 第 4 步验收门 PASS 报告 |
| `result_corrupted.json` | 负向测试的损坏输入 |
| `gate_report_fail.json` / `gate_report_fail.md` | 负向测试验收门 FAIL 报告（退出码 5） |

## 补充验证（未留存产物）

- 契约缺失的 case：scaffold 退出码 3，仍写出含 case_id / status=partial /
  notes 的最小保底 result.json；
- 字符串形态契约（`title: string (必填)` 逐行描述）：正确解析出 4 个字段，
  `contract_shape=string_schema`；
- 渲染校验失败（标题含 `<` 被 HTML 转义）：退出码 6，失败原因如实写入
  `render_error.json`。
