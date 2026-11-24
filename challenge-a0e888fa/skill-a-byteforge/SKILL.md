---
name: byteforge-storage-forensics
description: >-
  科研数据表存储/编码层故障的字节级取证与可逆修复。当案例给出"已发表汇总表转写件"
  并怀疑或确认存在注入的存储/编码故障（mojibake 双重编码、非 UTF-8 编码、BOM、
  混合行尾、错误分隔符、不可见字符、全角字符、哨兵缺失码、千分位/小数逗号歧义、
  科学计数法文本、数值内嵌单位）时使用。本技能先固证、再诊断、审批后修复、
  独立重算核验，然后才允许语义层清洗；绝不插补缺失/非法源值。
---

# byteforge：存储/编码故障取证与可逆修复

## 重心与边界

本技能只负责**字节→干净文本**这一层，并把每一步做成可复核证据：
诊断（字节级举证）→ 修复草案 → 审批 → 确定性修复 → 独立重算 + 往返核验。
语义层工作（缺失分类、单位换算、去重、异常判定、质量报告）在恢复表上进行，
严格依据案例自带的数据字典、单位/QC 规则与工单。**禁止**推断总体统计量、
**禁止**均值/中位数插补、**禁止**发明源数据中不存在的值。

三个脚本均为 Python 3 标准库、确定性、只读原始文件；技能默认安装在
`/skills/weekly-skill`（下文以 `$SK` 代指；若不在该路径，用
`find / -maxdepth 6 -name byte_scan.py 2>/dev/null` 定位后取其父目录的父目录）。

## 标准流程（按序执行，不可跳步）

### 0. 读案 + 固证 + 保底 result.json（最先做）

```bash
ls -laR /input; cat /input/case.json; cat task.md   # task.md 在工作目录
mkdir -p /app/work /app/output
```

- 记录 `case_id` 与 `output_contract` 的**每一个字段**；案例材料文件名以实际为准。
- 固证：对每个输入文件记录 `路径/字节数/sha256` 到 `/app/work/snapshots.json`。
- 立即写 `/app/output/result.json` 首版：`case_id` + output_contract 全字段占位
  + `"status": "in_progress"`；此后每完成一阶段增量刷新。**宁可部分诚实**。

### 1. 诊断

```bash
python3 $SK/scripts/byte_scan.py <数据表> --dict <数据字典，可选> --out /app/work/diag
```

读 `fault_report.md`（紧凑版）与 `suggested_repair_map.json`。故障类型与证据标准见
`references/fault_taxonomy.md`。

### 2. 审批（Agent 的判断点，不可省略）

复制草案为 `repair_map.json`，逐项裁决并置 `"approved": true/false`：

- score ≥ 0.8 且 before/after 样本自洽 → 批准；0.5–0.8 或 `ambiguous: true`
  → 必须对照字典/工单核定，无法核定者**不批准，改列隔离**；< 0.5 → 默认隔离。
- 哨兵 token（-999/NA/空白…）在本层**只计数不处理**；其语义由字典决定，
  留待语义层按工单处置。审批规则详见 `references/repair_playbook.md`。

### 3. 修复

```bash
python3 $SK/scripts/repair_apply.py <数据表> --map repair_map.json --out /app/work/repair
```

哈希不符、存在未批准项都会拒绝执行（退出码非 0）。产物：`recovered.csv`（规范
CSV：逗号、LF、UTF-8 无 BOM）+ `repair_log.json`（每项操作的 before/after 计数）。

### 4. 独立重算 + 往返核验

```bash
python3 $SK/scripts/roundtrip_check.py --original <数据表> \
    --map repair_map.json --recovered /app/work/repair/recovered.csv \
    --out /app/work/verify
```

退出码非 0 ⇒ 修复不可复现或不可逆，**不得进入语义层**；回到第 2 步修正审批。

### 5. 语义层清洗与交付（在 recovered.csv 上）

按案例工单完成缺失分类、单位规范化、去重、异常标记与质量报告；规则见
`references/repair_playbook.md` 末节"恢复后语义层清单"。质量报告的每个数字必须由
脚本从产物重算，不得手写。最终：`/app/output/result.json` 填满 output_contract
全部字段、`status` 如实（success/partial/failed），清洗表、台账、故障报告、
roundtrip_verdict.json 一并放入 /app/output。

## 异常处理

- 文件无法以任何候选编码解码 → byte_scan 退出码 3，result.json 记 `failed` 并说明。
- 千分位/小数逗号歧义无法核定 → 该列整体保留原字面值并列入 `review` 清单。
- 空表/单行表 → 诊断为 structure-only 报告，如实降级 partial。
- 时间不足 → 优先保证 result.json 合法 + 故障报告 + 已核验的 recovered.csv。

## 最小示例

`examples/` 内含一份**合成**演示表（双重编码 mojibake + NBSP + 全角数字 + 哨兵码
+ 分号分隔）与真实运行产物，命令见 `examples/README.md`。示例数据为合成，
不对应任何正式案例。
