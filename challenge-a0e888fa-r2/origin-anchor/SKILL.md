---
name: origin-anchor-arithmetic-forensics
description: >-
  当清洗对象是“已发表汇总表（aggregate table）的转写件”且被显式注入存储/编码故障、
  随附数据字典与按指标给出的单位/QC 规则和明确清洗工单时使用本技能。本技能利用汇总表
  自带的算术冗余结构（行/列合计、百分比闭合、mean=sum/n、加权均值、单位对偶列、字典
  物理界）构建恒等式网络，对注入故障做最小命中集定位与置信分级，并仅对“唯一可解”的
  单元格做等式反解式有限恢复。输出 consistency_report.md、suspect_map.csv、
  restoration_ledger.csv、cleaned.csv 与 digest.md。本技能不负责字节编码取证、不负责
  报告渲染、不负责运行时预算管理；严禁插补缺失值、严禁推断总体统计量、严禁依据标签
  补造数据。
---

# Origin Anchor：发表汇总表的算术自洽取证

## 1. 重心与边界

本技能的核心洞察：已发表汇总表自带算术冗余结构——合计等于分项之和、百分比等于
部分/总体×100、mean=sum/n、构成比闭合、字典给出的物理上下界与单位/QC 规则。注入的
故障会破坏这些恒等式；反过来，恒等式网络就是故障定位与有限恢复的锚点（anchor）。

本技能**只管**：结构挖掘 → 恒等式建网与评估 → 最小命中集故障定位与置信分级 →
唯一可解单元格的有限恢复 → 留痕交付。

本技能**明确不管**（由其他技能或工单其他条款负责）：

- 字节级编码取证（BOM、乱码字节序列的统计鉴定）——本技能只要求输入是 UTF-8
  工作副本并留痕，不做编码真伪仲裁；
- 报告渲染（HTML/PDF/图表）——本技能只产出 Markdown 与 CSV；
- 运行时预算管理（64 次请求 / 900 秒的调度）——runbook 的命令设计得尽量少而确定，
  但预算记账不是本技能的职责。

## 2. 铁律

1. **不插补**：缺失值、非法值一律不得用任何统计量或模型填补。
2. **不推断总体统计量**：不得由汇总统计量反推总体参数或假设分布。
3. **不依据标签补造数据**：唯一合法的恢复来源是“恒等式反解”，且须满足
   references/fault_localization.md 第 3 节的全部充要条件。
4. **原值必留痕**：任何改动记录旧值与新值；未恢复的可疑格原样保留并写入
   uncertainty；失败与无法解释处如实说明，宁可 partial 不可粉饰。

## 3. 路径说明

技能安装在 `/skills/weekly-skill`，下文以 `$SK` 代指技能根目录。运行前先定位：

```bash
SK=/skills/weekly-skill
if [ ! -f "$SK/scripts/consistency_check.py" ]; then
  SK=$(dirname "$(dirname "$(find / -maxdepth 6 -name 'consistency_check.py' 2>/dev/null | head -n1)")")
fi
echo "SK=$SK"; ls "$SK/scripts"
```

## 4. 运行契约

- 输入：`/input/case.json` 与工作目录中的 `task.md`（内含 output_contract）。
- 工作区：`/app/work`（中间产物、规范化副本、日志都放这里）。
- 交付：`/app/output`，其中 `result.json` 必须含 `case_id` 与 output_contract 声明的
  全部字段，含诚实的 `status`（success/partial/failed）、`sources`、`uncertainty`、
  change records（逐格旧值/新值/依据）。
- **最先落 result.json 骨架**（步骤 0），任何后续中断都留下合法的 partial 结果。

## 5. 分步 runbook

以下命令块可直接复制执行。`<表.csv>` 指案例给出的汇总表转写件在 /app/work 下的路径。

### 步骤 0：读案 + 固证 + 保底 result.json

```bash
mkdir -p /app/work /app/output
cat /input/case.json; echo; cat task.md 2>/dev/null || cat /app/work/task.md
# 原始字节固证（任何后续处理前先留指纹）
sha256sum /input/* 2>/dev/null | tee /app/work/input_sha256.txt
# 保底 result.json 骨架（先落盘，后续步骤结束时再用真实数字覆写）
python3 - <<'PY'
import json, pathlib
case = json.load(open("/input/case.json", encoding="utf-8"))
skel = {
    "case_id": case.get("case_id", "unknown"),
    "status": "partial",
    "sources": ["/input/case.json", "task.md"],
    "uncertainty": ["流水线尚未运行完毕，本骨架为保底结果"],
    "changes": [],
}
pathlib.Path("/app/output/result.json").write_text(
    json.dumps(skel, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("skeleton written")
PY
```

### 步骤 1：编码规范化为 UTF-8 工作副本（留痕）

```bash
python3 - <<'PY'
import hashlib, pathlib
src = pathlib.Path("/app/work/table_raw.csv")   # 按案例实际路径调整
raw = src.read_bytes()
used, text = None, None
for enc in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
    try:
        text = raw.decode(enc); used = enc; break
    except UnicodeDecodeError:
        continue
if text is None:
    raise SystemExit("无法解码，保留原字节并转入人工说明")
norm = text.replace("\r\n", "\n").replace("\r", "\n")
pathlib.Path("/app/work/table_utf8.csv").write_text(norm, encoding="utf-8")
pathlib.Path("/app/work/encoding_log.txt").write_text(
    f"source={src}\ndetected={used}\nsha256_raw={hashlib.sha256(raw).hexdigest()}\n"
    f"sha256_utf8={hashlib.sha256(norm.encode('utf-8')).hexdigest()}\n",
    encoding="utf-8")
print(f"encoding: {used}; utf-8 copy at /app/work/table_utf8.csv")
PY
```

### 步骤 2：结构挖掘

```bash
python3 "$SK/scripts/table_scan.py" /app/work/table_utf8.csv --out-dir /app/work
echo "exit=$?"   # 3 = 空表/无表头，转入人工说明并收尾为 failed/partial
cat /app/work/scan_report.md
```

### 步骤 3：据数据字典填 constraints.json

Agent 阅读案例随附的数据字典与单位/QC 规则，对照
`$SK/references/aggregate_structures.md` 第 3 节的 schema 填写
`/app/work/constraints.json`：字段角色（n/计数/百分比及其分子分母/mean/sum_mean_pairs/
单位对偶列）与物理界 bounds。**每条必须带 source 定位**（字典条目原文位置），
无法从字典确认的条目不写。可用 examples/constraints.json 作为格式范本。

### 步骤 4：恒等式建网 + 评估 + 最小命中集定位

```bash
python3 "$SK/scripts/consistency_check.py" /app/work/structure.json /app/work/constraints.json --out-dir /app/work
echo "exit=$?"   # 4 = constraints.json 校验失败（缺 source/字段不存在），回步骤 3 修正
cat /app/work/consistency_report.md
```

### 步骤 5：唯一可解单元格的有限恢复

```bash
python3 "$SK/scripts/restore_unique.py" /app/work/table_utf8.csv /app/work/structure.json \
  /app/work/equations.jsonl /app/work/suspect_map.csv /app/work/constraints.json --out-dir /app/work
cat /app/work/digest.md
```

### 步骤 6：交付 + 报告数字从产物重算

```bash
cp /app/work/consistency_report.md /app/work/restoration_ledger.csv \
   /app/work/suspect_map.csv /app/work/cleaned.csv /app/work/digest.md /app/output/
```

随后覆写 `/app/output/result.json`：**status、changes 条数、未解决项等数字必须从
产物重算**（restoration_ledger.csv 的行数即恢复格数；digest.md 的“仍违反等式”即
uncertainty 来源），不得凭记忆填写。判定口径：

- 全部违反等式被唯一可解恢复且复评全通过 → `success`；
- 有恢复但仍有未解决可疑格/违反等式，或仅完成定位未恢复 → `partial`；
- 空表、无法解码、constraints 校验失败且无法修正 → `failed`，附原因。

result.json 的 `changes` 数组逐格对应 restoration_ledger.csv 行：
`{cell, row_label, column_header, old_value, new_value, equation_ids, method}`；
`uncertainty` 数组列出未恢复的 primary 单元格及原因（取自 digest.md）。

## 6. 异常处理

| 情形 | 退出码 / 行为 | 降级动作 |
|---|---|---|
| 空表或无表头 | table_scan 退出码 3 | 不运行后续步骤；result.json 写 failed 并说明 |
| 无合计/小计行 | scan_report 警告 | consistency_check 自动只剩行内等式+字典界；报告中声明降级 |
| 字典缺物理界 | bounds 写空数组 | 置信不会出现 high；uncertainty 声明此局限 |
| constraints.json 缺 source / 字段不存在 / 索引越界 | consistency_check 退出码 4 | 回步骤 3 修正后重跑；不得绕过 |
| 等式大面积违反（命中集超过违反等式数一半） | consistency_check 退出码 0 | 疑为整体错位，禁止恢复；suspect_map 全标注，status=partial 并说明 |
| 等式全部无法评估（普遍缺值） | 退出码 0 | 如实报告 UNDEFINED；不定位、不恢复 |
| 恢复候选冲突 / 越字典界 / 非唯一可解 | restore 跳过该格 | 原值保留，原因写入 digest.md 与 uncertainty |

## 7. 最小示例指引

`examples/` 内置一张**人工编造的合成**临床试验风格汇总表（不对应任何正式案例）：
注入 2 处故障——合计行 n 格被改（唯一可解）、A/B 两组 responders 同时被改
（不可唯一解）。复现：

```bash
cd "$SK"
python3 scripts/table_scan.py examples/trial_table.csv --out-dir /tmp/oa
python3 scripts/consistency_check.py /tmp/oa/structure.json examples/constraints.json --out-dir /tmp/oa
python3 scripts/restore_unique.py examples/trial_table.csv /tmp/oa/structure.json \
  /tmp/oa/equations.jsonl /tmp/oa/suspect_map.csv examples/constraints.json --out-dir /tmp/oa
```

预期：定位到 3 个 primary 可疑格；restoration_ledger.csv 只含合计行 n 一格
（96→90）；A/B 两组 responders 保留原值并写入 digest.md 未恢复清单。
真实运行产物见 `examples/expected/`。
