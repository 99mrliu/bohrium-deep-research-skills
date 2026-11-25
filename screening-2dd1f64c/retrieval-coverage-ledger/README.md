# retrieval-coverage-ledger

文献筛选与智能排序挑战的 Skill 包。重心是**上游数据真实性与来源/遗漏审计**：交付物不是一堆筛选标签，而是一套建立在有限检索快照之上的台账——来源可追溯（哪条实际查询命中哪条记录）、逐查询产出、全记录恰好一次的会计恒等式、保守的重复/版本登记、以及显式的遗漏说明（有限快照、无实时库、不可声称全局召回）。

## 文件

- `SKILL.md` — Skill 定义：用途与重心、适用条件、运行契约与预算纪律（≤2 次模型调用、纯脚本退化路径）、输入输出、异常处理、方法限制与自查。
- `scripts/coverage_engine.py` — 台账引擎，**仅依赖 Python 3 标准库**，argparse 子命令：
  - `map`：宽容定位候选池与实际查询，逐条来源归因（显式字段 > 词面重叠推断 > 未归因登记），输出逐查询产出与缺失元数据登记。
  - `account`：按会计恒等式入账（未知 id 拒入 rejected_register、缺失补 pending、非法 quote 置 null，全部记入 change_records），构建重复/版本登记与遗漏说明，逐字段镜像 output_contract，产出 result.json。
  - `validate`：校验 case_id 回显、契约字段齐全、会计恒等式精确成立、quote 逐字子串、登记引用合法；PASS/FAIL + 退出码。
- `references/coverage-playbook.md` — 归因优先级、推断诚实规则、合并阈值、遗漏说明模板、会计修复规则、保守去重与夹具纪律的理由。
- `examples/minimal/` — 合成示例（`case.example.json` + `decisions.example.json` + 运行说明），含显式/推断/未归因记录、预印本-正式版重复对（带 fixture_note）、缺失元数据记录。

## 运行环境

Python 3（标准库即可，无第三方依赖）；正式运行契约见 SKILL.md（`/skills/weekly-skill` 安装路径、`/app/work` 工作目录、`/app/output/result.json` 交付）。

## 范围与限制

- 推断归因是词面重叠启发式，`matched_tokens` 即审计线索，语义误差如实写入 `uncertainty`。
- 快照之外的召回不可声称：无实时数据库，遗漏说明是一等交付物而非免责声明套话。
- 夹具标注（fixture_note）仅逐字存档为 provenance，绝不当作 ground truth；模糊疑似重复对只进人工复核队列，绝不自动合并。
- 判定的语义质量取决于那一次批量模型调用；本引擎保证的是来源可追溯、会计恒等、交付合规与可核验。
