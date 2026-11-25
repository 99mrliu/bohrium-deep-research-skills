---
name: xlang-translation-roundtrip-desk
description: 跨语言检索的受控翻译台账与回译质检（controlled translation ledger & round-trip QC）。管理 Agent 供给的术语译名条目（concept_id、源/目标语种、term、back_translation、翻译服务与版本、证据），对每条做回译一致性校验（回译与概念 label 或同语种变体的规范化 token 重叠），识别"词面对应、语义不同"的误译假阳性模式（term 与 label 词面相近但回译不一致 → surface-match-semantic-drift 风险标记），输出逐条使用策略（full-weight / half-weight / hold-for-review）与 concept×语种 缺口清单（to_translate）。当查询/术语/标题需要受控翻译、必须说清用了哪种翻译服务与版本、并保留译文与原文对照时使用；适用于 /input/case.json + task.md 的 Harbor 运行契约。
---

# 受控翻译台账与回译质检（xlang-translation-roundtrip-desk）

## 用途与适用条件

整句机翻查询的三类错误（术语被译成字面同义词、译文用词与原文用词不一致、译文与原文不同义）都源于**翻译过程不可追溯**。本 Skill 的重心是**翻译环节的台账化与质检**：每条译名都是一个带来源、服务、版本、回译证据的台账条目；回译不一致的条目降级使用而非删除；"词面相近但回译不符"的高风险条目显式标记，供人工复核。

本工具**绝不自行翻译**：译名只能由 Agent（可调用平台翻译服务或自身能力）以条目形式供给。不做：匹配、语种判定、版本归并。

## 运行契约

- 输入：`/input/case.json`（含 `case_id`、`output_contract`）、`/input/task.md`；
  Agent 编写的概念表 `concepts.json` 与翻译条目 `translations.json`。
- 工作目录 `/app/work`；最终 `/app/output/result.json` 含 `case_id` 与 `output_contract`
  全部字段；翻译台账作为 sources/evidence 引用；degraded/no-evidence 条目写入 uncertainty。
- 翻译服务名称与版本必须如实填写（含"模型自身翻译"这一来源）；不知道版本就写 unknown，
  不得编造。

## 调用方式

```bash
# 1.（Agent）从案例抽取概念，写 /app/work/concepts.json
#    {"concepts":[{"concept_id":"C1","label":"pyroptosis",
#      "variants":[{"lang":"en","term":"pyroptosis"}]}]}
# 2.（Agent）对每个 概念×目标语种 缺口供给译名，写 /app/work/translations.json
#    {"translations":[{"concept_id":"C1","target_lang":"pt","term":"piroptose",
#      "back_translation":"pyroptosis","service":"deepseek-chat",
#      "service_version":"2026-11","evidence":"title of /input/..."}]}

# 3. 质检
python3 scripts/translation_ledger.py --concepts /app/work/concepts.json \
    --translations /app/work/translations.json \
    --langs en,pt,es,de,ja,zh --out /app/work/ledger

# 4. 阅读 /app/work/ledger/roundtrip_report.md：
#    degraded 与 surface-match-semantic-drift 条目逐条人工裁定；
#    to_translate 清单决定补译或在 result.json 中声明缺口。
```

完全离线、仅标准库；数秒完成，不消耗模型请求。

## 输出

`/app/work/ledger/`：

- `ledger.json`：`entries[]`（原字段＋status∈{verified,degraded,no-evidence,invalid}、
  usage∈{full-weight,half-weight,hold-for-review}、roundtrip_score、risk、reason）、
  `to_translate[]`（缺口清单）、`counts`、`parse_notes`。
- `roundtrip_report.md`：人读质检表。

## 关键方法（详见 references/translation_qc_policy.md）

1. **回译校验**：back_translation 与概念 label、同语种既有变体分别算 NFKD 折叠后的
   token Jaccard，取 max 为 roundtrip_score；≥0.5 或有共同 token → verified。
2. **降级而非删除**：不一致 → degraded＋half-weight（仍参与检索，命中带标记）；
   无回译证据 → no-evidence＋half-weight；缺必填字段 → invalid＋hold-for-review。
3. **误译假阳性识别**：term 与 label 词面 token Jaccard ≥0.5 但回译不一致 →
   risk=surface-match-semantic-drift（如把 pyroptosis 译作葡语"morte celular"——
   词面像、语义漂移），这是人工复核的最高优先级。
4. **缺口显式化**：concept×目标语种 无变体且无译名 → to_translate；
   不补译的缺口必须在 result.json 的 coverage/uncertainty 中声明。

## 异常处理

| 情况 | 处置 |
|-|-|
| translations 文件缺失/损坏 | parse_notes 记录，全部 concept×语种 进入 to_translate |
| 条目缺必填字段 | status=invalid，hold-for-review，不参与检索 |
| 条目引用不存在的 concept_id | label 为空，回译只能比对同语种变体；reason 注明 |
| 服务/版本未声明 | 保留条目并加 note；result.json 的 sources 中如实写"未声明" |
| 回译为空串 | 视同无证据（no-evidence），不得当成"通过" |

## 自查方法

1. 每条 used 条目都有 status 与 usage，degraded/no-evidence 条数与 uncertainty 一致；
2. surface-match-semantic-drift 条目全部有人工裁定记录（接受/替换/放弃）；
3. to_translate 缺口与 result.json 声明的语种覆盖缺口一一对应；
4. 台账中没有任何一条 term 是脚本生成的（全部来自 Agent 供给文件）。

## 最小调用示例

见 `examples/example_walkthrough.md`（**合成示例**，非正式案例结果）。
