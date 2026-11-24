---
name: kbqa-answer-forge
description: 科研知识库问答的"带来源引用问答生产线"——问题分解为可验证子论断，BM25-lite 确定性检索（阴性检索同样留痕），每个论断绑定库内原文的逐字引文与版本坐标（file_id + SHA-256 前 8 位 + 行号区间），由确定性脚本逐条机器核验引文真实性，核验不过强制降级或改写后重验，最终由硬性闸门组装 result.json，模型无权手工把 status 改成 completed。Use when a task requires answering questions over a local scientific document library with verifiable sentence-level citations (带来源引用的问答, 证据回链, 逐句对应, 引用核验, 阴性检索, 多文件检索, /input/case.json, result.json).
---

# 带来源引用的问答生产线（kbqa-answer-forge）

重心在**答案侧**：回答里每个关键论断都必须携带可通过确定性脚本核验的
逐字引文与版本坐标；核验报告（citation_verification.json）是交付物的
一部分，评审可据此逐条回到原文核对。编目/索引只是取证前置，不是交付中心。

## 何时使用 / 不适用

适用：平台给出 `/input/case.json` + `/input/task.md` 与本地科研资料库，
要求多文件检索、带来源引用的问答、证据回链、对无依据问题明确说"没有"。
不适用：纯开放式写作（无库可引）；此类任务勿用本 Skill。

## 运行时合同（先读再动手）

1. 先读 `/input/case.json`、`/input/task.md`：`case_id`、问题列表、
   `output_contract` 决定 result.json 字段。
2. 工作区 `/app/work`；最终交付 `/app/output`：result.json（含 case_id、
   output_contract 全部字段、诚实 status/sources/uncertainty/change_log）
   + citation_verification.json（核验报告）。
3. 预算约 64 次模型请求 / 900 秒。脚本全是确定性的，不占模型预算；
   预算分配与收尾纪律见 references/answer_workflow.md 末节。

## 工作流（$SKILL=/skills/weekly-skill）

```bash
SKILL=/skills/weekly-skill

# 1) 读题 + 建索引 + 立刻落保底 result.json（status=partial）
python3 $SKILL/scripts/qa_init.py --input /input --work /app/work --out /app/output

# 2) 逐题逐检索式检索（零命中自动记入 retrieval_log.jsonl）
python3 $SKILL/scripts/qa_retrieve.py --work /app/work \
    --question-id q1 --query "<检索式>" --top 5

# 3) 模型写 work/citations.jsonl 与 work/answers.json（格式见
#    references/citation_contract.md），然后机器核验全部引文
python3 $SKILL/scripts/qa_verify.py --work /app/work --out /app/output \
    --citations /app/work/citations.jsonl

# 4) 按核验报告改写/降级（改写后重跑 3，直到 all_passed 或全部降级），再组装收尾
python3 $SKILL/scripts/qa_finalize.py --input /input --work /app/work --out /app/output
```

## 硬性规则

- 引文五元组缺一不可：file_id、sha8（版本坐标）、行号区间、逐字引文、
  所属论断；格式与失败处置见 references/citation_contract.md。
- 转述必须 `paraphrase: true` 且措辞明示；禁止把转述伪装成引文。
- 多版本材料只从当前版本取事实性引文（历史版本引用须明示用途）。
- 库中无依据的问题：answer 明确写"库中无依据"，uncertainty 写明缺什么；
  检索日志中的零命中记录是这一结论的可复核证据，禁止删除。
- 最终 result.json 不允许残留 pass=false 的引文；status 只能由
  qa_finalize.py 按闸门判定。

## 异常与失败处置

文件不可读/无文本层→该文件不可引，记入 uncertainty；PDF 缺 pdftotext→
记 extraction_unavailable 并继续其余文件；目录为空→qa_init 正常生成空
索引，result.json 标 partial 并说明；case.json 缺 output_contract→按
默认字段集交付并在 change_log 说明。脚本单文件级失败只影响该文件的
text_status，整体 exit 0。

## 自查清单

1. result.json 含 case_id 与 output_contract 全部字段？status 由 finalize 判定？
2. citation_verification.json 的 verdict 是 all_passed（或失败引文已全部降级）？
3. 每个数值论断的引文里真的含该数值？
4. "库中无依据"的问题是否都有对应零命中检索日志？
5. 抽样 2 条引文，能否只凭 [Fxx|sha8|L行] 在抽取文本中秒级定位？

最小调用示例见 [examples/minimal_example.md](examples/minimal_example.md)
（**合成示例**，非正式案例结果）。
