---
name: latex-template-migration
description: 当任务要求把已有 LaTeX 稿件迁入期刊、会议或学位论文模板（更换 documentclass、落实模板必填字段、保持版式合规）时使用本 Skill。核心分工：脚本只做确定性机械工作——clsinspect.py 解析目标 .cls/.sty 的接口、必填项与触发条件并对照稿件生成迁移计划，pkgconflict.py 按规则表检查宏包加载顺序、已知冲突对、与模板类的重复及模板禁用宏包并逐条给出处置建议，finalize.py 在迁移完成后做必填字段非空非占位检查、章节映射核对、真实 pdflatex 有界两轮编译验证、原稿与迁移稿的段落级最小 diff（证明正文意图未被改变），并归一化装配 result.json；Agent 负责阅读报告、理解 task.md、做全部语义判断与编辑改动。红线：脚本不改稿、不自动删宏包、不插占位字段；必填字段缺失或疑似占位时 finalize 判不合规不放行；契约字段缺材料给诚实的 null 并说明；pdflatex 缺失时诚实降级，禁止假装编译成功。不适用于从零写作（无既有稿件）、非 LaTeX 源文件的格式转换（如 docx）、以及完全没有模板文件且无任何版式要求的场景（此时只能做有限的结构检查）。
---

# latex-template-migration：稿件迁入模板并保持版式合规与原文意图

一句话定位：脚本探测与取证（模板接口、宏包合规、迁移后验证），Agent 主导
理解任务与执行迁移编辑，脚本最后收口装配可核验的交付物。

## 环境与预算

- 输入：`/input/case.json`（含 case_id 与 output_contract）、`/input/task.md`，
  材料按 case.json 指向解析（相对路径相对 /input）；case.json 缺失时遍历
  /input 并在报告中如实降级。
- 工作目录 `/app/work`（中间报告），最终产物与可编辑源码放 `/app/output`。
- 预算 64 次模型请求 / 900 秒 / 每次响应 16384 tokens。时刻表：
  1. 0–120 秒：读 task.md 与 case.json，跑 clsinspect 与 pkgconflict，
     通读三份报告；**先按契约落盘一版 result.json（可为 partial），再改进**；
  2. 120–480 秒：Agent 依据报告与 references/ 清单执行迁移编辑；
  3. 480–720 秒：跑 finalize，按 compliance 阻断项修复并重跑，直至合规；
  4. 至少保留 10 次请求余量应对修复迭代与最终目检。

## 运行流程

```bash
export SKILL_DIR=/skills/weekly-skill
mkdir -p /app/work/migration /app/output

# 第 1 步：模板接口解析 + 迁移计划（只读，不改稿）
python3 "$SKILL_DIR/scripts/clsinspect.py" --input /input --work /app/work

# 第 2 步：宏包合规检查（只给建议）
python3 "$SKILL_DIR/scripts/pkgconflict.py" --input /input --work /app/work

# 第 3 步：Agent 阅读 /app/work/migration/ 下三份报告与 /input/task.md，
#          把迁移稿写到 /app/work/migrated.tex（编辑全部由 Agent 完成）。

# 第 4 步：定稿——合规检查 + 真实编译 + 最小 diff + 装配 result.json
python3 "$SKILL_DIR/scripts/finalize.py" --input /input --work /app/work \
    --output /app/output \
    --original /input/manuscript.tex \
    --migrated /app/work/migrated.tex \
    --cls /input/<模板类名>.cls
```

材料文件名以实际案例为准；脚本均支持 `--manuscript/--original/--migrated/
--cls` 显式指定，未指定时按启发式定位并在报告中注明。

## Agent 判断规则

1. **必填字段逐项落实**：对照 template_interface.md 的必填项清单，在迁移稿
   导言区写出每个必填命令；值取原稿或 task.md 中已有事实，二者都没有时
   不得编造，在 result.json 的 uncertainty 中说明。
2. **宏包处置照单执行、逐条确认**：顺序问题调整加载先后；冲突对按模板
   指定二选一；与模板类重复的删除稿件侧调用；模板禁用的移除并改用模板
   自带机制。删除宏包前全文搜索其命令是否仍在使用。
3. **章节映射**：按 migration_plan.md 的映射表逐节确认；模板有专用结构
   命令时迁过去，否则同级别直映。标题文字一律不改。
4. **正文零文字改动**：只动导言区、文档类与结构命令；正文段落、表格
   内容、文献条目逐字保留。intent_diff 报告的任何文字改动都必须能解释
   为迁移需要，否则回滚。
5. **版式交给模板**：不手改页边距、栏数、行距、页眉页脚与章节样式；
   细则见 references/migration-checklist.md。

## 脚本产出说明

- `/app/work/migration/template_interface.md`：模板基类、类自带宏包、
  自定义命令/环境、文档选项、必填项及 `\ClassError` 触发条件、禁用宏包。
- `/app/work/migration/migration_plan.md`：章节映射表、必填项当前状态
  （已填/缺失/疑似占位）、稿件与模板宏包差异。
- `/app/work/migration/conflicts.md`：宏包问题清单（类型、严重级、
  文件:行号证据、处置建议）。
- `/app/output/compliance.json|md`：必填字段、章节映射、编译验证三项
  检查与总结论（合规才允许交付）。
- `/app/output/intent_diff.md`：段落级最小 diff，忽略纯命令/空白差异。
- `/app/output/result.json`：case_id 原样复制、契约字段逐字段镜像
  （四种历史方言均已归一化）、status（complete/partial/failed/blocked）、
  sources、uncertainty、artifacts（只列真实存在的文件）。

## 异常处置（识别→降级→记录）

- case.json 缺失或损坏：遍历 /input 降级，case_id 记 null 并写入
  uncertainty；result.json 照常尽早落盘。
- 模板 .cls/.sty 缺失：接口与必填项检查跳过，仅靠 task.md 文字要求，
  uncertainty 注明。
- pdflatex 未探测到：编译验证标记 skipped 与原因，status 至多 partial，
  禁止假装成功。
- 必填字段缺失/疑似占位、章节未映射、编译失败：compliance 判不合规，
  blocking_issues 逐条列出，status 记 partial，修复后重跑 finalize。
- 契约字段无对应真实产物：给 null 并在 uncertainty 说明，禁止填充编造值。

## 红线

- 脚本不修改稿件、不自动合并/删除宏包、不插入占位字段或原文句子；
  一切改动由 Agent 判断并执行。
- 示例只证明接口可运行，不代表正式案例表现；不预生成正式案例答案。
- 诚实空值优于填充；blocked/failed 也尽早落盘 result.json。
- 不谈评分、不谈分数复盘、不谈其他版本。
