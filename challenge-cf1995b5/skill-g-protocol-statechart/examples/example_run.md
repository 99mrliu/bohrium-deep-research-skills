# 合成示例运行记录

**合成示例输出，非正式测评结果。** 本例是 organizer canonical schema 的合成水样比色硝酸盐测定方案，不是真实实验。所有参数、QC 限值、资源、成本和情景结局均为合成规划输入，未开展湿实验。

## 成功运行与强制断言

在本 Skill 根目录执行：

```sh
./examples/run_example.sh
```

脚本从自身位置解析路径，先运行 bootstrap，再 compile，最后用 Python 标准库实际断言：required fields 完整、`result.status=complete`、三条精确路径、候选错误、resource note 解析/去重、作者元数据合并、planning-evidence locators、SVG XML 可解析以及合成 notice。任一断言失败都会使脚本非零退出，不是仅执行两个命令。

等价的前两步为：

```sh
python3 scripts/protocol_statechart.py bootstrap \
  --case examples/mock_case.json --task examples/task.md \
  --materials-dir examples/materials \
  --work-dir examples/work --output-dir examples/output
python3 scripts/protocol_statechart.py compile \
  --case examples/mock_case.json --task examples/task.md \
  --materials-dir examples/materials --spec examples/protocol_spec.json \
  --work-dir examples/work --output-dir examples/output
```

已实际运行：bootstrap 审计 3 个候选、读取 1 份合成材料、注册 4 台设备与 4 种材料；compile 返回 **0**，`validation.status=pass`、`result.status=complete`，11/11 状态可达，success/failure 终态均可达，3 个决策标签全部有注入路径覆盖，成功脚本所有断言通过。

三条路径的核对值（均非实测）：

| 情景 | 终态 | 状态访问 | 时间 min | 成本 CNY |
|---|---|---:|---:|---:|
| nominal | T_SUCCESS | 9 | 58 | 16.4 |
| recoverable_high_blank | T_SUCCESS | 12 | 66 | 17.1 |
| persistent_qc_failure | T_QC_FAIL | 9 | 26 | 6.4 |

已给情景逐分量最大值和保守图上界均为 **66 min / 17.1 CNY**，不超过 `resource_contract.budget_cap=80`。`deadline_days=1` 审核明确采用 `66 / 1440` 天的 elapsed-time 换算并在 within 范围内；该值不含预约窗口、排队或现实日历时间，输出要求资源负责人确认，不能理解为一天内一定可完成。

canonical 候选审计确实发现：

- `version=C1_ARITHMETIC_ERROR`：`unit_price*quantity` 重算 16.4，measurement 的申报 subtotal 为 1.8 而重算为 1.9，`total_cost=15` 也不一致；
- `version=C2_DOMAIN_ERROR`：33 degC 不在 20 起步、步长 5 的 range 网格；
- `version=C3_DOMAIN_AND_BUDGET_ERRORS`：成本 90/申报 80 且超过 budget_cap，温度和时间越出 range，`est_days=2` 超过 `deadline_days=1`。候选分钟字段为 null，未从 est_days 编造分钟。

`protocol_spec.candidate_revisions` 对三者均记录实际修订/拒绝理由；最终 result 保留这些记录。原始候选有错误不妨碍“修订后状态图工件”达到 complete，也不表示原候选被接受。

`equipment_domain_note` 含两个相同 JSON object，经 `JSONDecoder.raw_decode` 提取后只注册一台 note-only `EQ_COLORIMETER`；spec 的测量状态真实使用该 ID。其存在性和现实可用性仍须确认，解析成功不是资源批准。

## 三个负向测试（全部使用 /tmp 即时生成）

以下 harness 在 Skill 根目录运行，不在 examples/work 保留负向规格或输出。已实际执行并得到每项打印的 PASS：

```sh
TEST_TMP=$(mktemp -d "${TMPDIR:-/tmp}/protocol-statechart-negatives.XXXXXX")
python3 - "$TEST_TMP" <<'PY'
import copy, json, subprocess, sys
from pathlib import Path
root = Path.cwd()
tmp = Path(sys.argv[1])
base = json.loads((root / "examples/protocol_spec.json").read_text(encoding="utf-8"))

def run(name, spec, expected_rc):
    spec_path = tmp / (name + ".json")
    out = tmp / (name + "_output")
    spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    completed = subprocess.run([
        "python3", str(root / "scripts/protocol_statechart.py"), "compile",
        "--case", str(root / "examples/mock_case.json"),
        "--task", str(root / "examples/task.md"),
        "--materials-dir", str(root / "examples/materials"),
        "--spec", str(spec_path), "--work-dir", str(tmp / "work"),
        "--output-dir", str(out),
    ], check=False, capture_output=True, text=True)
    assert completed.returncode == expected_rc, (name, completed.returncode, completed.stdout, completed.stderr)
    load = lambda name: json.loads((out / name).read_text(encoding="utf-8"))
    return load("result.json"), load("validation.json"), load("simulation.json")

spec = copy.deepcopy(base)
next(s for s in spec["states"] if s["id"] == "D30_BLANK_QC").pop("else")
result, validation, simulation = run("missing_else", spec, 2)
assert result["status"] == "partial" and validation["status"] == "fail"
assert any("decision_explicit_else" in error for error in validation["errors"])
assert simulation["simulation_type"] == "not_run_due_to_validation_failure"
print("missing_else: PASS rc=2, partial/fail, simulation not run")

spec = copy.deepcopy(base)
scenario = next(s for s in spec["scenarios"] if s["scenario_id"] == "recoverable_high_blank")
scenario["decision_outcomes"]["D30_BLANK_QC"] = ["high_blank", "high_blank"]
result, validation, simulation = run("retry_overrun", spec, 2)
scenario = next(s for s in simulation["scenario_results"] if s["scenario_id"] == "recoverable_high_blank")
assert result["status"] == "partial" and validation["status"] == "fail"
assert scenario["termination"]["type"] == "detected_failure"
assert "S35_REBLANK exceeded max_visits 1" in scenario["termination"]["reason"]
print("retry_overrun: PASS rc=2, detected_failure at max_visits=1")

spec = copy.deepcopy(base)
spec["scenarios"] = [s for s in spec["scenarios"] if s["scenario_id"] != "persistent_qc_failure"]
result, validation, simulation = run("coverage_gap", spec, 0)
coverage = simulation["decision_branch_coverage"]
assert result["status"] == "partial" and validation["status"] == "pass_with_warnings"
assert coverage["complete"] is False
assert coverage["untested_decision_branches"] == [{"decision_id":"D30_BLANK_QC","label":"retries_exhausted"}]
print("coverage_gap: PASS rc=0, partial/pass_with_warnings, retries_exhausted uncovered")
PY
```

因此：缺 else 和重试越界均返回 **2**；覆盖缺口返回 **0** 但 result 仍为 partial，证明只检查进程返回码不够。

## 非合成 canonical 兼容 smoke

另已在 `/tmp` 即时生成一个最小的**非 synthetic** canonical case/spec：range/enum、`resource_contract`、`version`、`unit_price*quantity/subtotal/total_cost/est_days`、note-only 设备以及直接放在材料根目录的文本均走真实 bootstrap/compile。两命令返回 **0**，`result.status=complete`、`validation.status=pass`、候选 errors 为空；直接材料被读取且 case/task 未混入材料；`output_notice` 精确为“协议状态图与假设仿真输出；不是实测实验结果”，result/SVG 均不含“合成示例输出，非正式测评结果”。临时产物未放入 bundle。

## 保留文件与限制

- `examples/work/bootstrap_audit.json`：成功示例的候选、合同资源/note、材料和输入审计。
- `examples/work/protocol_spec.template.json`：bootstrap 生成的模板，含作者元数据与候选修订字段。
- `examples/output/{plan.json,plan.md,result.json,validation.json,simulation.json,statechart.svg,path_report.md}`：成功运行产物。
- 不保留任何负向测试生成物；SVG 是 UTF-8 XML 文本，不是二进制资源。

本例没有真实仪器 SOP、标准方法全文、实测吸光度/回收率、试剂库存或供应商价格，因此没有补造这些信息。`complete` 仅指合成规划工件与机器可检仿真完整，不表示方法科学有效性或实验成功。
