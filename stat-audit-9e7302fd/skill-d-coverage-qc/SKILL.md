---
name: coverage-qc-audit
description: >-
  当任务要求对研究论文做研究方法与统计审查(方法学审计、报告规范核查、出具结构化
  审查单)时使用本技能。区别于一般审查流程:以“六审查面×五检查面”台账做五态裁决
  (通过/问题/待复核/不适用/未检查)并由会计脚本强制完备性对账,同时以可复跑运行日志
  记录每一步的工具、输入输出文件哈希与裁决理由,使审查过程本身可审计、可被独立复跑,
  专门防止静默漏审、状态含糊与过程不可复现三类失效。
---

# 覆盖台账与运行日志的过程质量控制(coverage-qc-audit)

## 适用场景与边界

适用:对指定论文按 case.json 的 output_contract 出具研究方法与统计审查结果
(result.json + audit_sheet.md),并要求过程可核对、无静默遗漏的场合。

不做(越界即停止并向用户说明):
- 不检索外部文献数据库、不联网核查引文真伪(只能判“待复核”);
- 不润色、不改写论文、不代拟审稿意见以外的文本;
- 不下投稿/拒稿结论,只报告方法学与统计层面的发现;
- 数值重算非重心:仅核对文中自洽性(摘要 vs 正文 vs 表格),无法复算时判“待复核”。

## 运行环境

- 脚本仅依赖 python3 标准库,位于 `$SKILL_DIR/scripts/`。
- `$SKILL_DIR` 默认为 `/skills/weekly-skill`;若该路径不存在,回退为 SKILL.md
  所在目录(即本技能根目录)。绝不用 `find /` 搜索文件。
- 校验命令:
  - `python3 $SKILL_DIR/scripts/ledger_check.py ledger.json`
  - `python3 $SKILL_DIR/scripts/journal_check.py run_journal.jsonl --output-dir /app/output --ledger ledger.json`
- 参考文件:`references/checklists/*.md`(五份清单)、`references/coverage_matrix.md`
  (六面/五态/严重度表/完备性规则)、`references/guideline_map.md`(设计归类)、
  `references/journal_schema.md`(日志格式)。

## 工作流程(八步)

1. **定合同**:读 `/input/case.json` 与 `task.md`,提取 case_id 与 output_contract
   全部字段;立即在 `/app/output` 脚手架 result.json(case_id 已填,合同字段一律
   `PENDING::<字段名>`,status=partial),同时开 run_journal.jsonl 记 J-001。
2. **提取全文**:将论文(PDF 或文本)提取为纯文本,存于 /app/work,记录输入输出
   文件 sha256 入日志;提取失败立即把 result.json 置 failed 并交付,不留空壳。
3. **设计归类**:按 `references/guideline_map.md` 识别设计类型
   (RCT/队列/病例对照/横断面/诊断准确性/其他),确定默认“不适用”项;归类理由入日志。
4. **建台账骨架**:对五份清单逐项建单元(cell:item_id×facet×surface),状态全置
   “未检查”,reason 先留待填写;声明 counts 骨架。全集=清单适用项,宁多勿漏。
5. **逐项五态裁决**:逐单元裁决,状态语义与理由要求严格按
   `references/coverage_matrix.md`;“问题”必须同步登记 finding(原文位置/缺陷类型/
   严重度/依据/修改建议);每个状态变化写一条日志(journal_ref 指向该条)。
6. **会计校验**:运行 ledger_check.py。**不过不交付**:任何违规必须先修正台账再复验。
7. **组装审查单**:按合同字段组装 result.json 并写 audit_sheet.md;完备性声明中
   逐面报告六审查面×五检查面的覆盖计数——**无发现的面也必须声明“已检查,无发现”**,
   并解释“全通过”或“大量未检查”的成因。
8. **定稿与复验**:补全日志末条(final:true,outputs 列出交付文件),运行
   journal_check.py 复验;result.json 填写诚实 status(complete/partial/failed)、
   sources、uncertainty(含全部“待复核”事项)后交付。

## 注意事项

- **清单是底集不是上限**:清单之外的发现照常记录,ID 用 `X-新发现-N`,同样走
  五态与 finding 登记,不挤占清单项 ID。
- **全通过与大量未检查同样可疑**:两者都要在完备性声明中给出解释;“待复核”
  不是废纸篓,无法证实的疑似问题一律归“待复核”,绝不臆断为“问题”,也绝不编造
  原文位置或数据。
- **预算纪律**(64 次请求 / 900 秒):第 1、2 步完成后先落盘骨架;第 5 步先批量
  裁决、再统一补日志(时间戳保持非递增,哈希必须如实);预算不足时宁可部分单元
  留“未检查”并写明原因,以 partial 交付,也不得跳过校验脚本。
- **严重度只查表**:按 coverage_matrix.md 的 4 类×4 档固定表定级,“建议”类
  只允许低/提示;不做临时加刑或减刑。
- **examples 对齐**:`examples/` 下的合成示例(台账、日志、审查单)展示了交付物的
  目标形态与两个校验脚本的通过/失败样例,交付前对照其结构自查。
- 所有交付文件写 `/app/output`;中间产物(提取文本、台账、日志)写 `/app/work`,
  日志中的输出文件哈希以最终落盘内容为准。
