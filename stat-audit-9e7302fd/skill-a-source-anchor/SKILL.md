---
name: source-anchor-audit
description: >-
  当任务提供论文原文(PDF 或文本),要求逐条产出带原文位置、缺陷类型、严重度、
  依据、修改建议的研究方法与统计审查单时触发。区别于一般审查流程的核心能力:
  先做输入保真检测(source_integrity 门),再对每条发现的逐字引用做机器核验
  锚定(anchor_verify 门),无锚不立案、提取失败则诚实走材料不足分支,
  从源头消除因提取失真与定位不可验证导致的审查幻觉。
---

# 源锚定审查(source-anchor-audit)

本技能的重心在**上游**:输入保真 + 证据锚定。论点:审查幻觉多源于受损的文本
提取与不可验证的位置引用,因此每条发现必须挂在机器核验过的逐字锚点上,
且提取质量本身必须在审查之前被评估。

## 适用场景与边界

适用:评审环境提供论文原文(如 /input 下的 PDF 或文本),要求输出逐条带
原文位置/缺陷类型/严重度/依据/修改建议的审查单(audit_sheet.md)与
result.json 的研究方法与统计审查任务。

不做(明确边界):
- 不检索外部文献、不做查重或新颖性判断;
- 不润色、不改写论文;
- 不下投稿/录用结论;
- 数值重算只做轻量一致性提示(如分组例数加总、P 值与文字结论是否自洽),
  重心不在计算,不做统计复算引擎。

## 运行环境

- 脚本位于 `$SKILL_DIR/scripts/`,`$SKILL_DIR` 默认 `/skills/weekly-skill`;
  若该路径不存在,回退为「包含本 SKILL.md 的目录」。先探测后使用:
  `SKILL_DIR=/skills/weekly-skill; [ -f "$SKILL_DIR/SKILL.md" ] || SKILL_DIR=<本文件所在目录>`
- **严禁使用 `find /` 之类的全盘搜索**定位文件。
- 脚本仅依赖 python3 标准库;PDF 提取调用系统 `pdftotext`(poppler),
  不可用时脚本以非零码退出并给出清晰报错,此时改用任务环境提供的
  pdf-text-tool 生成 .txt 后再走本流程。
- 所有脚本支持 `--help`;任何失败均以非零退出码结束。

## 工作流程

1. **定合同、立即脚手架**:先读 /input/case.json 与 task.md,提取 case_id 与
   output_contract 声明的全部字段;立刻在 /app/output 写出 result.json 骨架:
   case_id 如实填入,合同字段一律置 `PENDING::*` 占位,`status="partial"`,
   sources/uncertainty 先给空结构。此后每完成一个阶段就增量更新该文件,
   保证中途超时也有诚实交付。
2. **提取全文并固证**:运行
   `python3 $SKILL_DIR/scripts/pdf_to_anchored_text.py <论文> --text-out anchored.txt --anchors-out anchors.jsonl --raw-out raw.txt`
   (输入为 PDF 时依赖 pdftotext;为 .txt 时直接使用)。三个产物落盘 /app/work,
   作为后续一切引用的唯一事实来源。
3. **保真度门**:运行
   `python3 $SKILL_DIR/scripts/source_integrity.py raw.txt --out integrity_report.json`。
   - `ok`:进入下一步;
   - `degraded`:可继续,但受损指标记入审查单与 uncertainty,涉受损页的发现
     提高核验等级;
   - `failed`(退出码 1):**材料不足分支**——不产出任何实质发现,result.json
     置 `status="failed"`,uncertainty 如实引用 fail_reasons,audit_sheet.md
     只写提取失败说明,立即定稿交付。
4. **五面审查产出候选发现**:按 references/facets_brief.md 的五面清单
   (研究设计/变量定义/统计方法/样本量/结果报告)逐面过原文。每条候选发现必须
   在写下时即从锚点文本中**复制粘贴** 12–40 字符的 quote(选段规则见
   references/anchor_protocol.md),并标注 facet、缺陷类型(事实错误/证据不足/
   规范问题/建议)、严重度、approx_page。候选发现写入 findings.jsonl。
5. **锚定核验门**:运行
   `python3 $SKILL_DIR/scripts/anchor_verify.py --findings findings.jsonl --raw raw.txt --anchors anchors.jsonl --out verified_findings.jsonl --rejects rejects.jsonl`。
   无锚不立案:只有通过核验(取得 page/line/char_start/char_end/context)的
   发现才进入审查单;被拒项按 anchor_protocol.md 第 4 节处置(重提取/重摘录/
   降级为待复核),处置后再送检。该脚本退出码 1 表示存在被拒项,属正常流程
   信号而非崩溃。
6. **组装审查单**:写 /app/output/audit_sheet.md。每条发现含
   原文位置(P{页} L{行} › 章节)/缺陷类型/严重度/依据(quote + 规范或方法学
   理由)/修改建议;区分事实错误/证据不足/规范问题/建议,无法证实者标
   「待复核」。末尾附**完备性声明**:送检数/通过数/拒绝数、每条 reject 的
   处置、integrity verdict 及受损项。
7. **定稿 result.json**:镜像 case.json 的 output_contract 形状,填齐全部
   字段;`status` 诚实取 complete/partial/failed;sources 列出实际使用的
   文件与脚本产物;uncertainty 如实写明提取质量、未覆盖面向、待复核项。

## 注意事项

- **预算纪律**:全程约 64 次模型请求、900 秒。步骤 1–3 是纯脚本,不耗模型;
  五面审查按 facets_brief 优先级分配注意力(先统计方法与结果报告),不要
  反复通读全文;每完成一阶段立即落盘增量交付,超时时 partial 也好过空交付。
- **模型不背原文**:quote 永远从锚点文本复制粘贴,严禁凭记忆复述或"整理"
  原文;字词改动一字即失去证据效力(anchor_verify 会拒绝)。
- **门是真实的**:source_integrity 的 failed 与 anchor_verify 的拒绝都以
  非零退出码+结构化文件表达,不得绕开、不得手工编造偏移量。
- **诚实优先**:不可验证 → 待复核;提取失败 → failed;预算不足 → partial
  并在 uncertainty 说明未覆盖范围。静默丢弃发现与静默保留无锚发现同为违规。
- **examples 对齐**:examples/ 为合成示例(非真实案件结果),演示期望行为;
  修改脚本后须重跑 run_example.sh 并同步 expected_output/。
- 参考文档:references/anchor_protocol.md(引用优先协议)、
  references/integrity_criteria.md(阈值与扫描件 playbook,与脚本常量一致)、
  references/facets_brief.md(五面问题清单)。
