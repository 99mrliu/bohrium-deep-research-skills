# criteria-matrix-aligner

文献筛选与智能排序（challenge-2dd1f64c）参赛 Skill 之一。**重心：上游判据保真**——从案例自带的标注标准逐字抽取判据注册表（附来源指针；无标准时派生判据诚实标注 `derived:true`），再以"记录 × 判据"逐格判定矩阵（met/unmet/unknown + 该记录标题或摘要的逐字引用）承载全部判定，标签、分值、名次由脚本确定性重算，与标注标准的一致性可逐格审计，编造引用过不了交付校验。

## 文件

- `SKILL.md` — 调用契约、四步运行手册（≤2 次模型调用）、预算纪律、异常处理、自查方法。
- `scripts/criteria_engine.py` — extract / decide / validate 三子命令，纯标准库，Python 3.8+。
- `references/criteria-playbook.md` — 判据注册表格式、判定语义与边界约定、批量矩阵调用措辞、面向一致性的判定准则。
- `examples/minimal/` — 可运行的最小合成示例（4 记录 × 3 判据，含预期 PASS 输出与退化路径），已标注为合成示例。

## 依赖与运行

仅 Python 3 标准库，无安装步骤。三条命令完成一次判据对齐的筛选交付（extract → decide → validate），见 SKILL.md 与 examples/minimal/README.md。

## 适用范围与限制

适用于平台固定案例（有限候选快照、全记录筛选、契约化交付、约 9 条记录）。判据的语义判定由调用方在一次批量模型调用中完成，本 Skill 保证判据来源保真、逐格留痕、结论可独立复算与交付合规；不负责底层数据库接入与全文阅读，判据语义判断的质量取决于模型调用本身。维护信息：随本仓库版本演进，变更记录写入结果 `change_records`。
