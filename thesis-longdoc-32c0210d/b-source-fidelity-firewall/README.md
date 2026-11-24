# source-fidelity-firewall

玻尔 Playground 竞赛题 challenge-32c0210d（学位论文与长文档写作）的
Skill bundle，重心为**上游数据真实性 / 事实保真防火墙**：

> 任何进入改后文本的事实必须可回溯到来源；任何编辑不得引入材料外
> 事实；引文逐字回源核验（脚本重验，不信任人工声明）。

## 内核机制（4 个脚本，python3 标准库，pdftotext 可选）

| 脚本 | 职责 |
|-|-|
| `scripts/extract_facts.py` | 从章节 Markdown 挖掘事实锚点 → `facts.json`：带单位数字、术语/缩写首次定义、`[n]` 引文、图表编号引用，每条含 `id/type/value/file/line` |
| `scripts/ground_evidence.py` | 逐条回源定位：优先材料目录（.txt/.md 直读，.pdf 自动 pdftotext）找逐字 quote，找不到回退原始工作稿（W16 设定下工作稿即事实底稿，`origin=working_chapters`）；写出前脚本重新包含校验 `verification` → `evidence_map.json` |
| `scripts/fact_diff_guard.py` | 编辑后把关：改后文本的数字 token/缩写/`[n]` 引文若不在 改前∪材料∪evidence_map → `fabrication_token`；新增含数字/引文句子无证据覆盖 → `unverified_new_sentence`。有 flag 即非零退出 |
| `scripts/make_result.py` | 运行时读 case.json `output_contract.fields` 逐字段填充（evidence 字段填 evidence_map 路径+统计），原子写 `result.json`，含 case_id/status/sources/uncertainty/change records，诚实 partial |

规范文档：`references/fact_grounding.md`（事实类型、定位策略、origin
语义、`【待确认：…】` 标注格式）、`references/evidence_map.schema.json`。

## 合成示例

`examples/synthetic/`（**SYNTHETIC EXAMPLE — 合成示例，非正式案例结果**）：
自造 3 个"固态电解质界面"短章节 + 实验记录材料 + 1 条改写工单。
`run_example.sh` 一键跑通 extract → ground → 模拟编辑（**故意把 85%
注入为材料外的 92%**）→ guard 捕获（`guard_report_injected-fault.json`，
退出码 1）→ 修复 → guard PASS → make_result。`expected/` 由真实运行
固化，脚本结尾自动 diff 校验确定性。

```bash
cd examples/synthetic && ./run_example.sh
```

## 快速使用（真实案例）

```bash
S=/skills/weekly-skill
python3 $S/scripts/extract_facts.py --chapters /input/chapters --out /app/work/facts.json
python3 $S/scripts/ground_evidence.py --facts /app/work/facts.json \
  --materials /input/materials --chapters /input/chapters --out /app/work/evidence_map.json
# …编辑 /app/output/edited_chapters/ …
python3 $S/scripts/fact_diff_guard.py --before /input/chapters \
  --after /app/output/edited_chapters --evidence /app/work/evidence_map.json \
  --materials /input/materials --out /app/work/guard_report.json
python3 $S/scripts/make_result.py --case /input/case.json \
  --evidence /app/work/evidence_map.json --guard /app/work/guard_report.json \
  --edited-chapters /app/output/edited_chapters --changes /app/work/changes.json \
  --out /app/output/result.json
```

详见 `SKILL.md`（含异常矩阵与诚实 partial 规则）。
