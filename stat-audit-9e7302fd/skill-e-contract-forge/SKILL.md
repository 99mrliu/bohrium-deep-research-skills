---
name: contract-forge-audit
description: >-
  研究方法与统计审查的下游交付工程技能。当任务要求按 case.json 的
  output_contract 交付 result.json 与审查单（audit sheet）时触发。差异化能力：
  把输出契约编译为机器可校验的 schema，第一分钟生成 result.json 保底骨架，
  交付前机器校验（字段齐全/类型匹配/零伪造 PENDING/status 诚实），
  并从同一份 findings 数据同源渲染 Markdown + 自包含 HTML 审查单，杜绝交付物漂移。
---

# contract-forge-audit：输出契约编译与交付物渲染校验

## 适用场景与边界

**适用**：评估器按 case 提供 `case.json`（含 `output_contract`）+ `task.md` + 论文
材料，要求交付 `result.json`（含 case_id 与契约声明的全部字段、诚实 status、
sources、uncertainty）与可检视的审查单（audit_sheet.md，发现须含
原文位置/缺陷类型/严重度/依据/修改建议）的任务。

**本 skill 不做**：
- 不检索外部文献、不做事实性外部核查；
- 不润色论文、不改写原文；
- 不下投稿/录用结论（只给方法学与报告规范层面的修改建议）；
- 定性判断的深度不是本 skill 的重心——但五面审查（研究设计/变量定义/
  统计方法/样本量/结果报告）**仍须全部走完**，无发现也要如实记录。

本 skill 的重心是消灭最常见的静默失败：result.json 缺契约字段、形状错误、
虚报 complete；以及审查单无法检视、与 result.json 数据漂移。

## 运行环境

- 脚本位于 `$SKILL_DIR/scripts/`；`$SKILL_DIR` 默认 `/skills/weekly-skill`，
  未设置时回退为本 SKILL.md 所在目录。可用：
  `SKILL_DIR="${SKILL_DIR:-/skills/weekly-skill}"; [ -d "$SKILL_DIR/scripts" ] || SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"`（在 skill 根目录执行时）。
- **严禁 `find /`** 查找文件；路径一律由 case.json / 环境变量 / 脚本参数给出。
- 全部脚本仅依赖 Python 3 标准库（`argparse/json/os/sys/html`），无需联网、
  无需安装任何包；均支持 `--help`；失败一律非零退出。
- 工作目录 `/app/work`，交付目录 `/app/output`；尽早写盘、增量更新。

## 工作流程

1. **读案 + 立即脚手架（第一分钟内保底）**：读 `/input/case.json` 与
   `task.md`，然后立刻运行
   `python3 $SKILL_DIR/scripts/contract_scaffold.py --case /input/case.json --outdir /app/work`
   生成 `contract_schema.json` 与 `result.json` 骨架（case_id 已填、契约字段
   置 `PENDING::<field>` 哨兵、status=partial、sources=[]）。核对 stderr 打印的
   契约来源；若为 fallback，重读 task.md 人工确认交付要求。把骨架复制到
   /app/output 作为保底交付物。
2. **提取全文**：把论文材料（PDF 或文本）提取为可检索文本存于 /app/work，
   记录实际读取的来源清单（供 sources 字段）。
3. **五面审查**：按 `references/facets_brief.md` 的提问清单逐面过原文，产出
   `/app/work/findings.jsonl`，每行一键 JSON：
   `{id, facet, category, severity, location, quote, message, fix, status}`，
   每条必须带定位与逐字引用；缺陷类型四分（事实错误/证据不足/规范问题/建议）；
   无法核实者 status 标 `待复核`，绝不删去或改写为定论。
4. **同源渲染三件套**：
   `python3 $SKILL_DIR/scripts/render_audit_sheet.py /app/work/findings.jsonl --outdir /app/output`
   一次产出 `audit_sheet.md`（按严重度→审查面分组 + 汇总表 + 待复核专区）、
   自包含 `audit_sheet.html` 与机器可读 `audit_findings.json`。findings 有更新
   就重跑本步。
5. **增量填写 result.json**：每完成一个契约字段就整体替换其 PENDING 哨兵并
   存盘；findings 数组字段从 `audit_findings.json` 取数填入，保证与审查单同源。
6. **交付前机器校验**：
   `python3 $SKILL_DIR/scripts/contract_validate.py --result /app/output/result.json --schema /app/work/contract_schema.json --case /input/case.json --report /app/output/validation_report.json`
   有违例就修复并重跑，直到 exit 0 或如实降级 status。
7. **终检定稿**：按 `references/delivery_checklist.md` 逐项核对；填实
   `sources`（只列真实读过的）、`uncertainty`（写明方法局限与待复核项）、
   诚实 `status`；把 `contract_schema.json`、`validation_report.json` 一并留档
   于 /app/output。

## 注意事项

- **三件套同源渲染防漂移**：`audit_sheet.md` / `audit_sheet.html` /
  `audit_findings.json` 必须由同一份 findings.jsonl 一次渲染；渲染后任何一边
  都不得手工再改；result.json 的 findings 字段从 `audit_findings.json` 取数。
- **status=complete 必须零 pending**：契约字段全部真实填写、无残留
  `PENDING::` 哨兵、`pending_reasons` 为空，校验器对此强制检查。
- **材料不足走 failed 分支**：保留已确认部分，未完成字段在 `pending_reasons`
  登记具体人工理由，**绝不伪造**数据、引用或来源。
- **预算纪律（64 请求 / 900 秒）**：骨架先行、增量写盘；剩余约 1/4 预算时
  停止扩展新发现，转入校验与终检；写文件不占模型请求，不要攒到最后。
- **examples 对齐**：`examples/` 内为合成示例（SYNTH-DEMO-001），
  `run_example.sh` 演示 scaffold→render→validate 全链路（含故意损坏件的
  失败路径）；真实运行行为应与其一致，行为不符时先查脚本版本再查输入。
- 详细契约语义见 `references/output_contract_guide.md`。
