---
name: dict-compiler-rules-from-dictionary
description: >-
  当任务给出随案数据字典、按指标给出的单位/QC 规则与明确清洗工单，要求对被注入
  存储/编码故障的已发表汇总表转写件做可审计清洗时使用。核心做法：用编译器把字典
  与工单文本机械编译为带出处（文件+行号）的可执行规则，Agent 的自由裁量被压缩到
  只剩一处——对编译器无法解析的行在 resolutions.json 中做裁决，且每条裁决必须引用
  字典行号；执行引擎只执行“编译产物+已批准裁决”，没有出处的规则一律拒绝。适用于
  强调出处可核验、禁止无据规则、禁止插补与禁止推断总体统计量的科研数据清洗场景；
  不适用于无字典、需要自由判断或需要统计推断的场景。
---

# dict-compiler：从数据字典编译清洗规则

## 重心与边界

本技能的重心是**规则知识工程**：不让 Agent 手写规则再执行，而是把案例自带的
数据字典、单位/QC 规则与工单文本**机械编译**为可执行规则——以知识抽取代替自由
判断。Agent 唯一的裁量点是 `parse_report.md` 中的未解析/歧义项，且每条裁决必须
引用字典行号。

流水线（四个确定性组件，Python 3 标准库，无网络，同输入必得同输出）：

1. **编译** `scripts/compile_dictionary.py`：字典/工单文本 → `draft_rules.json`
   （每条规则带 source 文件+行号+原文）+ `parse_report.md`（逐行登记）。
2. **裁决**（人工/Agent）：只处理未解析项 → `resolutions.json`
   （approve/adjust/reject + 依据行号 + rationale）。
3. **校验** `scripts/validate_rules.py`：合并、出处核验（无出处 → 退出码 4）、
   生成 `coverage_matrix.csv` 三视图与 `rules.final.json`（含 gaps 缺口清单）。
4. **执行** `scripts/execute_rules.py`：确定性执行 → `cleaned.csv` +
   `ledger.csv`（逐格：行/字段/旧值/新值/rule_id/source 行号）+ `digest.md`
   （数字从产物重算）。

## 铁律

- **无出处不执行**：任何规则必须能追溯到字典/工单的具体行号；`validate_rules.py`
  核验失败即退出 4，该批次规则一律不得执行。
- **不插补**：缺失/非法源值只做分类标记（置空 + QC 标记），绝不填入任何替代值。
- **不推断总体统计量**：不做均值、中位数、分布估计等任何跨行统计推断。
- **不依据标签补造数据**：标签/备注列只作为原样保留的文本，不得用来反推数值。
- **失败与无法解释处必须如实说明**：覆盖缺口、未解析行、无法解释的值一律写入
  `result.json` 的 uncertainty 与 `digest.md`，不得静默跳过。

## 路径说明

技能安装位置 `/skills/weekly-skill`。设环境变量：

```bash
SK=/skills/weekly-skill
if [ ! -f "$SK/scripts/compile_dictionary.py" ]; then
  SK=$(dirname "$(dirname "$(find / -maxdepth 6 -name 'compile_dictionary.py' 2>/dev/null | head -1)")")
fi
ls "$SK/scripts"   # 应见 compile_dictionary.py validate_rules.py execute_rules.py
```

## 运行契约

- 输入：`/input/case.json` 与工作目录中的 `task.md`（含 output_contract）。
- 工作区：`/app/work`；最终交付：`/app/output`。
- `result.json` 必须含 `case_id` 与 output_contract 声明的**全部字段**，含诚实的
  `status`（success/partial/failed）、`sources`、`uncertainty`、change records。
- **诚实 partial**：任何字段未覆盖、任何工单条目无法执行、任何值无法解释，都
  降级为 partial 并逐条说明，不得虚报 success。
- **骨架先行**：开工先写 result.json 骨架（全部字段占位），避免预算耗尽时无
  可交付物；随后逐步填充。
- 预算：64 次模型请求 / 900 秒。编译、校验、执行、digest 均由脚本完成，不要
  手工重算数字。

## 分步 runbook

### 0. 读案 + 固证 + 骨架

```bash
mkdir -p /app/work /app/output
cp /input/case.json /app/work/
cd /app/work
cat task.md            # 摘出 output_contract 字段清单
sha256sum /input/case.json task.md > /app/work/input_hashes.txt   # 固证
```

定位案例中的数据字典、单位/QC 规则、工单文本与待清洗数据（可能在 case.json
内嵌、也可能是独立文件），逐一落盘为 `/app/work/dictionary.md`、
`/app/work/workorder.md`、`/app/work/measurements.csv`。立即写 result.json 骨架：

```json
{
  "case_id": "<从 /input/case.json 读取>",
  "status": "failed",
  "sources": [{"file": "/input/case.json", "sha256": "<见 input_hashes.txt>"}],
  "uncertainty": ["pipeline 未运行，骨架占位"],
  "change_records": {"ledger": null, "count": 0}
}
```

> 骨架的 status 先置 failed，最后按事实改写为 success 或 partial；
> output_contract 要求的其余字段一并占位，宁缺勿假。

### 1. 编码规范化

```bash
python3 - <<'EOF'
from pathlib import Path
for p in Path("/app/work").glob("*.md"):
    raw = p.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
        try:
            t = raw.decode(enc); break
        except UnicodeDecodeError:
            continue
    if t != p.read_text(encoding="utf-8", errors="replace"):
        p.write_text(t, encoding="utf-8")
        print("normalized:", p, enc)
EOF
```

去 BOM、统一 UTF-8。**不得**改动数据单元格内容；任何字符级改动必须记入
result.json 的 change records。

### 2. 编译

```bash
python3 "$SK/scripts/compile_dictionary.py" \
  --dictionary /app/work/dictionary.md \
  --workorder  /app/work/workorder.md \
  --out /app/work
# 退出码 0=正常；3=字典与工单均未编译出任何规则/条目（见“异常处理”）
```

### 3. 裁决（Agent 唯一裁量点）

读 `/app/work/parse_report.md` 的“未解析/歧义项”表，逐条写
`/app/work/resolutions.json`：

```json
{
  "resolutions": [
    {
      "target": "U001",
      "action": "adjust",
      "rule": {"kind": "range_qc", "field": "<字段>",
               "params": {"lo": 0, "hi": 100, "lo_inclusive": true, "hi_inclusive": false}},
      "rationale": "<为何如此裁决，必须落在字典原文语义上>",
      "source": {"file": "/app/work/dictionary.md", "line": <U001 的行号>}
    }
  ]
}
```

- `approve` / `adjust`：给出合法 rule（kind ∈ sentinel_missing / range_qc /
  physical_bound / lod_below / unit_scale / dedup）。
- `reject`：该未解析行不产生规则，rationale 写明原因（如“附录未随案提供”）。
- `source.file`/`source.line` 必须与 parse_report 中该未解析项的位置**完全一致**，
  否则 validate 退出 4。
- 无法确定语义的，一律 reject 并在 uncertainty 中说明，**绝不猜测**。

### 4. 校验

```bash
python3 "$SK/scripts/validate_rules.py" \
  --draft       /app/work/draft_rules.json \
  --resolutions /app/work/resolutions.json \
  --data        /app/work/measurements.csv \
  --out /app/work
# 退出码 0=通过；4=存在无出处/出处不符规则或非法裁决 → 修复后重跑，不得绕过
```

读 `coverage_matrix.csv` 三视图（定义见 `$SK/references/coverage_matrix.md`）：
未覆盖字段 → 原样保留；无法执行的工单条目 → 写明原因。这些缺口已在
`rules.final.json` 的 gaps 中，第 6 步须抄入 result.json 的 uncertainty。

### 5. 执行

```bash
python3 "$SK/scripts/execute_rules.py" \
  --rules /app/work/rules.final.json \
  --data  /app/work/measurements.csv \
  --out /app/work
# 输出 cleaned.csv / ledger.csv / digest.md；退出码 0=正常，5=输入不合法
```

### 6. 交付

```bash
cp /app/work/cleaned.csv /app/work/ledger.csv /app/work/rules.final.json \
   /app/work/parse_report.md /app/work/coverage_matrix.csv /app/work/digest.md \
   /app/output/
```

填实 result.json：`status`（无缺口且全部工单条目 covered → success，否则
partial 并逐条说明）、`sources`（字典/工单/数据文件 + 每条规则的行号出处汇总）、
`uncertainty`（gaps 全量 + 未解释值）、change records（ledger.csv 路径与条数、
去重丢弃数、缺失标记数，数字从 digest.md 抄，不手算）。

## 异常处理

| 情形 | 处置 |
| --- | --- |
| 字典全无法解析（compile 退出 3） | 不手写规则顶替。逐行人工裁决：为每行写 approve/adjust 裁决（引用行号），或裁决 reject 并以 failed/partial 如实交付。 |
| 字段在字典中缺失 | coverage 自动列为 uncovered_field → 原样保留；写入 uncertainty，不得自行发明规则。 |
| 工单条目无对应规则 | coverage 列为 workorder_gap → 写明“无法执行原因”写入 uncertainty，status 降为 partial。 |
| 单位未知（换算系数缺失且内置表无此单位对） | compile 登记为未解析项；裁决 approve 时给出 factor（须引用工单/字典行号），否则 reject 并说明。 |
| validate 退出 4 | 存在无出处或出处不符的规则/裁决；修复 resolutions.json 后重跑，**不得绕过**。 |

## 最小示例指引

`examples/` 提供一个完整合成示例（**全部人工编造，不对应真实实验**）：
`dictionary.md`（Markdown 表+条目混合，含 2 处故意留下的歧义）、`workorder.md`
（5 条工单）、`measurements.csv`（对应注入故障）、`resolutions.json`（对 2 个
歧义行的裁决）、`expected/`（真实运行产物）。复现命令见 `examples/README.md`。
语法细节见 `references/dictionary_grammar.md`，覆盖矩阵定义见
`references/coverage_matrix.md`。
