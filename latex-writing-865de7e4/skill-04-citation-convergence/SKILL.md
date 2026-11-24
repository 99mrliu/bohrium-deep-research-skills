---
name: latex-citation-convergence
description: 当任务涉及 LaTeX 工程的交叉引用与参考文献完整性时触发——例如修复 undefined citation/reference、核对 \cite/\ref/\label/.bib 的引用图谱、检查 bib 条目字段是否满足样式要求、或需要多轮 latex+bibtex/biber 编译使警告收敛到零。核心能力：scripts/citeaudit.py 不编译即静态构建引用图谱（含多键 \cite、可选参数），给出未定义引用的正文 file:line 与最接近 bib 键候选（标注弱匹配）、未定义/重复 label、未被引用条目、按 entrytype 的字段缺失与 \cite 顺序重复；scripts/citebuild.py 在独立构建目录执行 latex→bibtex/biber→latex 有界多轮编译，以相邻两轮警告集合相同为收敛判据，给出每个引用键 resolved/unresolved+原因（缺条目/缺字段/bibtex 报错）与警告轮次曲线；scripts/finalize.py 装配 /app/output（citation_map.md、报告、rounds.json）并按 output_contract 四种历史方言归一化生成 result.json。分工：脚本只做确定性诊断、编译验证与装配；改不改引用键、补不补字段、删不删未引条目等语义判断由 Agent 完成。红线：脚本绝不自动改稿、绝不自动删 bib 条目、绝不低置信度重指向引用；无法解析的引用必须如实列出，不得静默忽略或删除；编译工具缺失时诚实降级而非假装成功。不适用于纯排版无参考文献的文档、非 LaTeX 文稿（Word/Markdown）或文献综述内容创作本身。
---

# LaTeX 引用图谱完整性与多轮编译收敛

一句话定位：用脚本确定性构建 \\cite/\\ref/\\label/.bib 引用图谱并做多轮收敛编译验证，Agent 依据报告做语义判断与修改，最终交付「每个引用点 ↔ bib 条目 ↔ 最终状态」全链路的引用映射。

## 环境与预算

- 运行目录约定：输入 `/input`（case.json、task.md、材料），工作目录 `/app/work`，交付目录 `/app/output`。下文用 `SKILL_DIR` 表示本 Skill 安装目录（如 `/skills/weekly-skill`）。
- 预算：64 次模型请求 / 900 秒 / 单次响应 16384 tokens。建议时刻表：

| 阶段 | 时间预算 | 动作 |
| --- | --- | --- |
| 诊断 | 0–120 秒 | citeaudit 静态审计 + citebuild 首轮编译探测 |
| 修复 | 120–600 秒 | Agent 读报告、理解 task.md、逐条修改 .tex/.bib |
| 验证 | 600–750 秒 | 重跑 citeaudit + citebuild 至收敛 |
| 交付 | 尽早一版、750 秒前定稿 | finalize 装配 result.json，先交付再增量改进 |

## 运行流程（命令可直接复制）

```bash
# 0. 读输入（case.json 缺失时遍历 /input 降级，finalize 会自动处理）
cat /input/case.json /input/task.md

# 1. 静态引用图谱审计（不编译；pdflatex 缺失也能跑）
python3 "$SKILL_DIR/scripts/citeaudit.py" \
    --project /input/project --work /app/work
# 输出：/app/work/citation_graph.json + /app/work/citation_report.md

# 2. Agent 阅读 citation_report.md 与 task.md，逐条判断并手工修改 .tex/.bib
#    （脚本不改任何稿件）

# 3. 多轮收敛编译验证（独立构建目录，不污染原工程）
python3 "$SKILL_DIR/scripts/citebuild.py" \
    --project /input/project --work /app/work \
    --build-dir /app/work/build --engine pdflatex --max-rounds 6
# 输出：/app/work/rounds.json（含警告轮次曲线、每键最终状态）+ citebuild_report.md
# 退出码：0 收敛且零未解析；2 仍有未解析引用；3 编译工具缺失（诚实降级）

# 4. 修复后重复 1 和 3，直至警告收敛到零或确认剩余项不可解析

# 5. 装配交付（契约归一化 + result.json）
python3 "$SKILL_DIR/scripts/finalize.py" \
    --case /input/case.json --work /app/work --out /app/output \
    --project /input/project
```

工程目录与 .bib 位置以 `/input/case.json` 的 materials 指向为准（相对路径相对 `/input`）。

## Agent 判断规则（脚本不做的事）

1. **未定义 \\cite**：看 citeaudit 报告第 1 节。强匹配候选（相似度 ≥0.8）多为拼写错误——核对文献主题后改正 \\cite 键；弱匹配或没有候选时**不得**重指向，应判断是「确实缺条目」（从原始材料核实后补 .bib 条目）还是「多余引用」（与 task.md 要求无关时删句子的引用而非删键）。
2. **重复 \\label**：保留语义正确的一处，其余改名并同步所有 \\ref。
3. **未被引用的 bib 条目**：先判断是漏引（正文应补 \\cite）还是备查（保留原样）。脚本绝不自动删除。
4. **bib 字段缺失**：对照 `references/bib-field-rules.md` 与任务指定样式（GB/T 7714、IEEE、APA 等），从原文/PDF 核实后补全；核实不到的字段保持空缺并在 uncertainty 中说明，**禁止编造**。
5. **\\cite 顺序**：数字编号样式（unsrt、GB/T 7714 顺序编码制）下参考文献表按首次引用排序，如任务要求特定顺序，用 citeaudit 第 5 节的首次出现顺序核对。
6. 每改完一轮重跑 citeaudit + citebuild 验证，不要批量改完才验证。

## 脚本产出说明

- `citation_graph.json`：机器可读全量图谱（引用点、label、bib 条目及字段、汇总计数）。
- `citation_report.md`：五节诊断——未定义引用（file:line + 候选键）、未定义/重复 label、未被引用条目、字段缺失表、\\cite 顺序与重复；只含建议。
- `rounds.json`：每轮工具/返回码/三类警告集合、`.blg` 警告与错误、收敛标志、警告轮次曲线 `curve`、每键最终状态 `final.key_status`（`resolved` 或 `unresolved（原因）`，原因分缺条目/缺字段/bibtex 报错三类）。
- `citation_map.md`：交付物，正文每个引用点 ↔ bib 条目 file:line ↔ 最终状态（标注是否经编译验证）。
- `result.json`：`case_id` 原样复制；output_contract 逐字段镜像（四种方言均可归一化，缺材料字段给 null + uncertainty 说明）；`status` 据实（complete/partial/blocked/failed）；`artifacts` 只列真实存在文件。

## 异常处置（识别 → 降级 → 记录）

| 异常 | 处置 |
| --- | --- |
| pdflatex/bibtex/biber 缺失 | citebuild 退出码 3，rounds.json 标 `compile_unavailable`；citeaudit 静态报告照常交付，result.json 记 uncertainty「未经编译验证」 |
| case.json 缺失/损坏 | finalize 遍历 /input 记录文件清单，case_id 置 null，status 据实给 blocked/partial |
| .bib 缺失或 \\bibliography 指向错误 | citeaudit 报告 bib_files 为空并提示；citebuild 在 .blg 捕获 `couldn't open database file` |
| 达到轮次上限仍不收敛 | rounds.json 记 `converged=false` 与最终警告集合，result.json 标 partial，禁止谎称收敛 |
| 任何脚本异常 | finalize 也会先落盘一份 failed 的 result.json，再排查 |

## 红线

1. 脚本绝不自动修改 .tex/.bib、绝不自动删除 bib 条目、绝不按相似度自动重指向引用；所有改动由 Agent 判断并执行。
2. 未解析引用必须如实列在 rounds.json / citation_map.md / result.json 中，不得静默忽略，不得为让警告清零而删引用键。
3. 契约字段缺材料时给 null + uncertainty 说明，禁止填充编造值。
4. 编译工具缺失时明确标注「编译验证不可用」，禁止假装成功。
5. 示例均为自造合成示例，不代表正式案例表现；trace 与文档不谈评分。
