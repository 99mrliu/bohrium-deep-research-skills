---
name: stat-recompute-audit
description: >-
  当用户提交论文（PDF/文本）并要求做研究方法与统计审查、核对统计量与 p 值、
  检查置信区间/百分比/样本量是否自洽时触发。区别于一般定性审稿：本技能用
  确定性标准库脚本重算论文中全部可算统计量（t/F/χ²/z/r、OR/HR/RR、百分比、
  CI、样本量反算），模型零心算，数值结论一律以脚本输出为准。
---

# 统计重算审查技能（stat-recompute-audit）

## 适用场景与边界

**适用**：对单篇论文做研究方法与统计规范审查，产出带原文定位的审查单；
尤其擅长发现显著性翻转、p 值数值偏差、CI↔p 矛盾、百分比不自洽、
不可能值、缺自由度/缺精确 p 等可计算缺陷。

**不做**：
- 不检索外部文献、不做查重或引文核验；
- 不润色文字、不代写修改稿；
- 不对是否可投稿下结论；
- 混合效应模型、贝叶斯方法、复杂生存分析量等超出脚本内核的统计量，
  只做规范层面审查并标「待复核」，绝不臆算。

## 运行环境

- 脚本位于 `$SKILL_DIR/scripts/`；`SKILL_DIR` 默认 `/skills/weekly-skill`，
  若不存在则取本 SKILL.md 所在目录。禁止 `find /` 之类全盘搜索。
- 仅依赖 python3 标准库；不需要联网、不需要 pip 安装。
- 三个脚本均支持 `--help`；硬失败（输入不可读等）以非零码退出；
  空抽取/空输入只告警不崩溃。运行示例见 `examples/run_example.sh`。

## 工作流程

1. **定合同、先脚手架**：读取 `/input/case.json` 与 `task.md`，记下
   `case_id` 与 `output_contract` 声明的全部字段。立即在 `/app/output/`
   写出 `result.json` 初版：`case_id` 已填，合同字段一律填 `PENDING::*`，
   `status: "partial"`。此后每完成一步就增量更新，防超时丢失。
2. **提取全文**：将论文 PDF 转为纯文本（`pdftotext -layout` 或
   pdf-text-tool），产物存 `/app/work/paper.txt`；文本 case 直接使用。
   保留行号语义（脚本输出的 `line` 即该文本行号）。
3. **数值部分一次跑完**（先自检，再抽取，再重算）：
   ```bash
   python3 "$SKILL_DIR/scripts/statmath.py"            # 自检须全 PASS
   python3 "$SKILL_DIR/scripts/extract_stats.py" paper.txt -o stats.jsonl
   python3 "$SKILL_DIR/scripts/recompute.py" stats.jsonl -o findings.jsonl
   ```
   自检任一 FAIL 或脚本硬失败：数值部分整体降级为「待复核」，记入
   `uncertainty`，继续定性审查，不得中断任务。
4. **五面非数值审查**：按 `references/facets_brief.md` 的研究设计 /
   变量定义 / 统计方法 / 样本量 / 结果报告五面过一遍全文；每条发现
   必须有章节 + 表号/图号 + 原句定位。
5. **交叉核对防脚本误报**：
   - 对 findings.jsonl 中每条 critical/major，抽读其 `context` 字段，
     确认引用的统计量真实存在于原文（防止抽取错位、表格串列）；
   - 另在原文随机反查 2 处 p 值，确认抽取无系统性漏抽/错挂；
   - 确认误报的条目在审查单中删除并注明原因，不得直接照抄脚本输出。
6. **组装审查单**：将脚本发现（经第 5 步核销）与五面发现合并为
   `/app/output/audit_sheet.md`；每条含 原文位置 / 缺陷类型
   （事实错误·证据不足·规范问题·建议）/ 严重度 / 依据 / 修改建议；
   无法核实的标「待复核」。
7. **定稿 result.json**：按 case 的 `output_contract` 镜像填充全部字段；
   `status` 据实填 complete/partial/failed；`sources` 列所审论文与
   所用脚本；`uncertainty` 说明待复核项与降级原因。

## 注意事项

- **数值结论以脚本为准**：模型全程零心算；任何 p 值、CI、百分比、
  样本量的判断引用 `findings.jsonl` 的 `recomputed` 字段。
- **冲突处理**：模型判断与脚本冲突时，先查抽取错位（context 串行、
  表格错列、全角字符、重复统计量错挂 p 值），确认无误后信脚本。
- **严重度与缺陷性质相称**：映射规则见 `references/recheck_rules.md`
  （显著性翻转/CI↔p 矛盾=critical，数值偏差不改结论/百分比不自洽=major，
  缺 df/缺精确 p=minor，无法重算=待复核）；不得随意升格或降格。
- **抗误报**：脚本已按报告值舍入区间做区间算术比较，边缘差异
  （如 p=.050 对 p=.051）不会误报；不要再以“更接近”为由追加数值发现。
- **诚实报告**：宁可 partial + 待复核，不得编造数值或定位；
  部分完成也要保证 result.json 合法且字段齐全。
- **示例对齐**：`examples/` 为合成示例，运行 `run_example.sh` 的结果
  应与 `expected_output/` 一致；脚本行为变更后必须重跑并同步。
