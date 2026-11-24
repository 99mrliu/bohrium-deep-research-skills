---
name: kbqa-kb-renderer
description: 科研知识库问答的"下游渲染与交接工程"——把编目、版本关系与问答结果渲染成一套第三方可导航的知识交接包（知识库地图 knowledge_index.md、机器可读编目 catalog.csv、版本与重复说明、每题一张带来源坐标的答案卡），再用确定性机检脚本验证全部互链有效、编目与磁盘重算一致、答案卡内每条引文坐标回验通过；渲染不新增事实、机检不过不许交付。Use when a document-library QA or organization task requires a handover-quality navigable deliverable with machine-checked links and citations (知识沉淀, 交接, 可检索清单, 编目, 答案卡, 证据回链, 链接校验, /input/case.json, result.json).
---

# 下游渲染与交接工程（kbqa-kb-renderer）

重心在**交付侧**：同样的答案，裸 result.json 和一套互链完好、坐标可机检的
交接包，对评审与后续使用者是两个量级的产品。本 Skill 负责后者：渲染 +
机检。检索与作答逻辑从简（关键词命中 + 模型选段），因为本 bundle 的价值
主张是"交接质量由机器把守"，而不是再造一条检索流水线。

## 何时使用 / 不适用

适用：`/input/case.json` + 资料库，任务要求可检索可交接的清单/知识结构、
带来源问答，且交付物会被他人继续使用（评审、交接、归档）。
不适用：只要求 result.json 数值正确、无人读交付要求的纯机评任务。

## 运行时合同

1. 先读 `/input/case.json`、`/input/task.md`：case_id、问题、output_contract。
2. `/app/work` 中间产物；`/app/output` 交付：result.json（case_id +
   contract 全部字段 + 诚实 status/sources/uncertainty/change_log）、
   render_report.json、handover/（交接包）。
3. 预算 64 次模型请求 / 900 秒：扫描/渲染/机检皆确定性脚本；第 1 步即落
   骨架 result.json（partial）；render_report pass=false 时 status 只能
   是 partial。

## 工作流（$SKILL=/skills/weekly-skill）

```bash
SKILL=/skills/weekly-skill

# 1) 轻量编目 + 问题解析 + 保底 result.json
python3 $SKILL/scripts/render_scan.py --input /input --work /app/work --out /app/output

# 2) 模型作答：写 /app/work/answers.json（格式见下），论断带
#    [Fxx|sha8|La-Lb] 坐标与逐字引文；坐标从 work/render_catalog.json
#    与 work/extracted/Fxx.txt 中取

# 3) 渲染交接包
python3 $SKILL/scripts/render_kb.py --work /app/work --out /app/output

# 4) 机检：互链 + 编目磁盘重算 + 引文回验；不过则修 answers/重渲染
python3 $SKILL/scripts/link_check.py --input /input --work /app/work --out /app/output
```

answers.json 格式：`{"answers":[{"question_id","answer",
"claims":[{"claim","evidence":[{"file_id","sha8","line_start","line_end","quote"]}]}],
"uncertainty":[...]}]}`。交接包布局与答案卡规范见
references/deliverable_layout.md；风格规则见 references/style_rules.md。

## 硬性规则

- 渲染不新增事实：答案卡内容只能来自 answers.json 与编目；缺证据回问答
  阶段补，不在卡片上手写。
- 机检三类不过即不交付：断链、catalog.csv 与磁盘哈希不符、引文回验失败
  （含 file_id 不存在、版本坐标不符、引文非逐字）。
- "库中无依据"的问题也渲染答案卡，答案段写"库中无依据"并在不确定性段
  写明缺什么——拒答也是交接内容。
- catalog.csv 禁止手工编辑；改编目必须重跑 render_scan。

## 异常与失败处置

0 个可读文件 → 交接包照常生成但首页明示无可读文件，result.json partial；
PDF 无文本层/权限不足 → 该行 catalog.csv 标 text_status，version_notes.md
如实列出；问题列表为空 → handover 只含编目与地图，result.json partial 并
说明。脚本 exit 0。

## 自查清单

1. render_report.json 的 pass=true？
2. knowledge_index.md 四段齐全（文件树/版本/问题索引/编目链接）？
3. 抽查 2 张答案卡：引文坐标能回到 extracted 文本原文？
4. result.json 的 status 与 render_report 一致，uncertainty 非空（有就说
   有）或确为干净完成？

最小调用示例见 [examples/minimal_example.md](examples/minimal_example.md)
（**合成示例**，非正式案例结果）。
