# QC 缺陷清单与修复策略

qc_loop.py 按本清单逐项检查 `/app/output/result.json` 与 `/app/work/checkpoints/`。
原则：**能安全修复的自动修复并写 change_log；不能安全修复的绝不硬改，逐条写入
uncertainty**。修复后的 result.json 仍保持确定性序列化。

| 编号 | 缺陷 | 严重度 | 可自动修复？ | 修复/处置策略 |
|---|---|---|---|---|
| Q0 | result.json 缺失 | critical | 否 | 直接 ok=false，提示先运行 warden.py；不臆造骨架以外的内容 |
| Q1 | case_id 缺失或为占位值 | critical | 是（有来源时） | 依次尝试从 `--case` 指定的 case.json、stage0 checkpoint 恢复；恢复不了则写 uncertainty，不编造 |
| Q2 | 必备顶层字段缺失（case_id/status/seed/candidates/edges/sources/evidence_records/uncertainty） | major | 是 | 按类型补空值（空表/空串/partial），并写 uncertainty 说明该字段为 QC 后补 |
| Q3 | output_contract 字段未逐字段镜像 | major | 是 | 从 case.json 读取契约键，缺失键补 null 镜像；丢字段违反运行契约，必须补齐 |
| Q3b | 契约镜像字段为 null | minor | 否 | 契约允许空值，但需 uncertainty 提示人工确认该字段确实无对应产物 |
| Q4 | 记录或边缺少 `source: {file, pointer}` | major | 否 | locator 不可事后补造（补了就是伪造溯源），逐条列明细写入 uncertainty，要求回源数据修复 |
| Q5 | stub 比例 > 50% | major | 否 | 写入 uncertainty 警示语料覆盖度不足；stub 本身是诚实产物，不删除 |
| Q6 | status 与实际完成度不符 | major | 是（单向） | 仅自动执行 `ok → partial` 的保守校正（completed_stage<3、budget_limited 或缺 stage3 checkpoint 时）；`partial → ok` 不自动提升，仅提示人工确认 |
| Q7 | checkpoint 链断裂（stage 号不连续） | minor | 否 | 写 uncertainty 说明 `--resume` 将回退到最近完整阶段；不重建缺失 checkpoint |

## 严重度语义

- **critical**：结果不可评或身份不明（Q0/Q1）；存在未决 critical 时 `ok=false`。
- **major**：违反运行契约或诚实性要求（Q2–Q6）；自动修复成功则视为闭环，未决 major
  使 `ok=false`。
- **minor**：不影响可评性但需人工知悉（Q3b/Q7）；不阻塞 `ok=true`。
- **info**：检查通过的记录，留在报告中供审计。

## change_log 约定

每次自动修复追加一条 `{"time": …, "change": "Qx: 描述"}` 到 qc_report.json 的
change_log，并同步写入 qc_report.md。时间戳只进 QC 产物，不进 result.json 本体
（result.json 内仅追加 uncertainty 文本）。

## 退出码

- `0`：无未决 critical/major（stdout 打印 `ok=true`）；
- `1`：存在未决 critical/major 或 result.json 缺失（stdout 打印 `ok=false`）。

## 扩展指引

新增检查项时遵守三条：编号递增；能修复才修复、修复必须保守（只向"更诚实"方向改，
如 ok→partial，绝不反向）；不可修复项一律走 uncertainty，不得静默丢弃。
