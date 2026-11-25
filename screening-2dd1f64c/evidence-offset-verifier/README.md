# evidence-offset-verifier

文献筛选与智能排序任务的**可解释性工程与反编造校验** Skill bundle。每条筛选决定必须携带逐字证据引文，脚本把引文锚定到该记录自身标题/摘要的字符偏移区间（`{field, start, end, surface_form}`），校验器逐条重算不变式 `record[field][start:end] == surface_form`——编造或错引的"证据"无法幸存：进入 `rejected_register`（附 difflib 最近邻匹配供一次修复），其决定无条件降级为 pending。交付物是经核验的理由卡片（`rationale_cards.md`）与 `result.json`，而不是裸标签。

## 文件

```
SKILL.md                          技能说明（用途/适用条件/运行契约与预算纪律/输入输出/异常处理/方法与限制）
scripts/evidence_engine.py        引擎：anchor / cards / validate 三个子命令（Python 3 标准库，零依赖）
references/anchoring-spec.md      锚点 schema、匹配与偏移映射规则、拒绝与降级策略、卡片模板、置信度指引、限制
examples/minimal/                 合成示例（case + decisions + 运行说明，含退化路径与拒绝路径演示）
README.md                         本文件
```

## 运行方式

```bash
python3 scripts/evidence_engine.py anchor   --case CASE.json [--decisions decisions.json] --out anchored.json
python3 scripts/evidence_engine.py cards    --case CASE.json --anchored anchored.json --out result.json [--cards-md rationale_cards.md]
python3 scripts/evidence_engine.py validate --case CASE.json --result result.json   # PASS=0 / FAIL=1
```

仅需 Python 3 标准库（argparse / json / difflib / pathlib），无第三方依赖，无网络访问。

## 范围与限制

- 证据来源仅限记录的标题与摘要；不获取全文，不访问实时数据库，不声明有限快照之外的召回。
- 脚本保证的是证据锚点的机械可核验性、全记录覆盖与确定性排序；判据语义质量取决于 Agent 的批量判定。
- 案例中以 `fixture_note` 等字段标注的夹具（合成重复导出、冲突观点）仅作 provenance 引用，绝不作为 ground truth。
- `examples/minimal/` 为合成演示数据，不冒充正式案例结果。
