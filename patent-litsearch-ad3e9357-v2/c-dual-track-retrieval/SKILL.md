---
name: dual-track-retrieval-lab
description: 面向专利与技术文献主题检索的检索策略工程技能——以"概念块 + 意图标签"构造可解释、可复现的检索式（R1–R9 规则校验与双轨渲染），在专利轨与非专利文献（NPL）轨分别执行不同的检索逻辑与去重键（专利按同族/公开号、论文按 DOI/标题），再以 PRISMA 风格完成逐条决策筛选，所有计数一律由脚本依据命中与决策重新计算并强制产出遗漏说明，从而把"召回是否充分、遗漏出在哪里"变成可审计的证据链而非口头声明。
---

# dual-track-retrieval-lab：检索策略与召回控制实验室

## 用途与适用条件

本技能用于**主题检索类**任务：给定研究问题，构造可解释的检索式，在本地材料（专利记录、
论文、USPTO 传真文本等）上双轨执行，并完成 PRISMA 风格筛选与遗漏说明。核心交付不是
"找到几条"，而是"检索式如何构造、每轨如何执行与去重、每个计数如何被脚本重算、遗漏
出在哪里"。

适用：主题/技术路线检索、新颖性/查新的初筛、综述证据收集。
不适用：号码精确提取与规范化、引文逐条对账、法律状态/许可核查（由其他技能承担；
本技能遇此类任务按"案例路由表"降级处理并标注局限）。

## 运行时契约

- 评测方将本 Skill 安装于 `/skills/weekly-skill`，用官方 DeepSeek Harness 运行 3 个
  固定隐藏案例。运行时输入为 `/input/case.json` + `/input/task.md` + 材料文件
  （专利记录、USPTO 传真 PDF、对比论文）。**必须读取真实文件内容，绝不允许凭文件名
  臆测内容。**
- 工作目录 `/app/work`；交付 `/app/output/result.json`，含 `case_id`、诚实的
  `status`（ok/partial/failed）、`sources`、`uncertainty`、`change_records`，并镜像
  `output_contract` 的**全部**字段（未填字段一律置 `null` 并在 `uncertainty` 注明）。
- 预算 64 次请求 / 900 秒：**先用 `scaffold_result.py` 生成诚实的 partial 骨架，
  再逐步改进**，确保任何时刻都有可交付结果。
- 绝不编造命中或计数；零命中是合法交付，但必须附扫描范围说明（脚本 meta 自带）。
- 打包约束：≤50 个 UTF-8 文本文件，单文件 ≤500KB，总量 ≤2MB，无符号链接、无二进制。
- 脚本退出码：`0` 成功；`2` 检索式规格/决策输入违规；`3` 计数一致性失败。

## 调用方式（有序管线）

在 `/app/work` 下依次执行（示例路径以本 skill 根目录为基准）：

1. **骨架先行**：`python3 scripts/scaffold_result.py --case /input/case.json --out /app/output`
   生成镜像契约的 partial 骨架。
2. **撰写检索式规格**：把研究问题拆成 ≥2 个概念块，逐词标注 intent，写入
   `query_spec.json`（模式见 `references/query_construction.md`）。
3. **校验**：`python3 scripts/query_build.py validate --spec query_spec.json`
   （违规 → 退出 2 并打印规则编号，修正后重跑）。
4. **双轨渲染**：`render --track patent` 与 `render --track npl` 各渲染一次；
   npl 轨自动丢弃 classification_codes 并输出 NOTE（R5）。
5. **本地执行**：`python3 scripts/corpus_search.py run --spec query_spec.json
   --roots <材料目录...> --out hits.json`，得到带 file+line 定位的命中、
   去重后记录、排除与未命中清单。
6. **逐条决策**：为每条去重后记录写 `decisions.json`
   （`{doc_id, decision: include|exclude, reason}`，exclude 必须给理由）。
7. **筛选与重算**：`prisma_screen.py screen` → `prisma_screen.py report`
   （可选 `--claim` 校验自报计数；不一致 → 退出 3）。
8. **回填结果**：把检索式、候选、PRISMA 计数、遗漏说明经
   `scaffold_result.py --fill fill.json [--status ok]` 合入 `result.json`。

## 输出

- `result.json`：镜像 `output_contract` 全部字段；未填字段为 `null` + uncertainty 注明。
- `hits.json`：每条命中含 `doc_id / track / matched_terms（块+词）/ locator(file+line)
  / dedup_key`，附扫描范围与零命中词项统计。
- `prisma.json`：identification / screening / included 三阶段计数（全部脚本重算）、
  按理由汇总的排除分布、遗漏说明模板。

## 关键方法

1. **概念块 + 意图标签**：研究问题 → ≥2 个概念块（AND 连接），块内为同义词项
   （OR 连接）；每词必标 `core/variant/classification/exclusion`。排除只走顶层
   `exclusion_terms` 且逐条附理由——禁止裸 NOT（R4）。
2. **双轨不同逻辑**：patent 轨支持分类号过滤（R5）、按同族号（无则规范化公开号）
   去重；npl 轨无分类号概念、按 DOI（无则规范化标题）去重。两轨命中分别计数。
3. **计数永远脚本重算**：PRISMA 各阶段数字由 `prisma_screen.py` 依据 hits +
   decisions 重算；调用方自报数字仅作 `--claim` 对账，不一致即失败（exit 3）。
4. **遗漏说明强制**：未覆盖概念块、零命中词项、查询层排除、筛选层排除（按理由）
   必须写入 `omissions_note`；模板由脚本生成，禁止留空。

## 案例路由表

| 案例类型 | 路由 | 做法 |
| --- | --- | --- |
| 主题检索（主场景） | 完整管线 | 概念块规格 → 双轨渲染执行 → 决策筛选 → PRISMA 重算 → 遗漏说明 |
| 号码类任务（给公开号/专利号查记录） | 降级路径 | 单块规格：块内含号码词项（intent=core），validate 会因 R1 拒绝时改用 `corpus_search` 之外的直接定位，并在 `uncertainty` 标注"本技能为词组匹配引擎，号码规范化非其职责，召回以字面匹配为限" |
| 混合任务 | 分层 | 主题部分走完整管线；号码部分按降级路径，结果在 `query_log` 分轨记录 |

## 异常处理表

| 异常 | 信号 | 处理 |
| --- | --- | --- |
| spec 违规（R1–R8） | validate/render/run 退出 2，打印规则编号 | 按编号修正 spec 后重跑；禁止绕过校验强行渲染 |
| 零命中 | run 成功但 `records` 为空 | 合法交付：填 `status=partial/ok`，附 meta 中的扫描范围与零命中词项，绝不编造命中 |
| 缺 decision | screen 退出 2 并逐条列出缺失记录 | 补全 decisions.json（每条去重后记录一条）后重跑 |
| exclude 无理由 | screen 退出 2 | 补 `reason`；无理由的排除不可审计，视同未完成 |
| 自报计数与重算不一致 | report 退出 3（MISMATCH 明细） | 以脚本重算为准修正自报数字；禁止反向改脚本迁就数字 |
| case.json 形态异常 | scaffold 打印 WARN | 骨架按默认契约字段生成，`uncertainty` 注明解析异常 |

## 自查

```bash
python3 scripts/selfcheck.py   # 22 项断言全部 PASS 才退出 0
```

覆盖：合法 spec 校验与双轨渲染（含 npl 丢弃分类号的 NOTE）、R4/R2 反面样例、
渲染可复现性（R9）、语料执行的命中与同族合并、缺 decision 退出 2、PRISMA 精确
计数重算、篡改 claim 退出 3、骨架镜像契约。

## 最小示例

```bash
cd /skills/weekly-skill
python3 scripts/query_build.py validate --spec examples/fixtures/query_spec_valid.json
python3 scripts/query_build.py render --spec examples/fixtures/query_spec_valid.json \
    --track patent --out /tmp/q_patent.txt
python3 scripts/corpus_search.py run --spec examples/fixtures/query_spec_valid.json \
    --roots examples/fixtures/corpus --out /tmp/hits.json
```

完整逐步演示（含真实输出）见 `examples/example_walkthrough.md`；
方法论细节见 `references/query_construction.md` 与 `references/dual_track_screening.md`。
