# 受控翻译与回译质检策略（translation QC policy）

## 台账条目契约

每条译名必须包含：`concept_id`、`target_lang`、`term`（必填）；
`back_translation`、`service`、`service_version`、`evidence`（强烈建议）。
没有服务与版本信息的翻译不可复现——保留条目但记 note，result.json 的
sources 中如实写"未声明服务"。脚本永远不生成 term。

## 回译一致性

- 规范化：NFKD 去变音＋小写＋token 化（拉丁与 CJK/假名 token）。
- `roundtrip_score = max(jaccard(back_translation, label), max over 同语种变体)`。
- score ≥ 0.5 或回译与 label 有共同 token → `verified`，full-weight。
- 否则 → `degraded`，half-weight：保留在查询与匹配中（漏检比假阳性更难发现），
  但命中带标记、置信减半、计入 uncertainty。
- 无 back_translation → `no-evidence`，half-weight，reason 写明
  `round-trip:no-evidence`；空串按无证据处理，不得视为通过。

## 误译假阳性（surface-match-semantic-drift）

模式：term 与概念 label 词面相近（token Jaccard ≥ 0.5，多见于同源词/音译），
但回译指向另一概念。例：pyroptosis → 葡语译名 "morte celular programada"
（词面含 "celular"，回译为 "programmed cell death"——细胞焦亡只是程序性
细胞死亡的一种，上位词替代导致检索发散）。此类条目是人工复核最高优先级：
接受（注明理由）、替换（新条目，旧条目标 superseded）、或放弃（该语种进缺口清单）。

## 降级原则

降级不是删除。被降级译名仍参与检索的理由：跨语言检索中召回损失不可见、
假阳性可在复核阶段剔除；但每条降级命中都必须可追溯到本条目的 status 与 reason。

## 缺口处理

`to_translate` 是 concept×目标语种 的真实缺口（既无变体也无译名）。
Agent 可补译（新条目再走一遍质检）或在 result.json 中声明该语种覆盖缺口；
两者之外不允许第三种"静默跳过"。

## 版本与复现

翻译服务输出随版本漂移；service_version 不知道就写 `unknown`。
同一 概念×语种 允许有多条条目（不同服务）；质检逐条进行，下游可按
usage 与 status 选择，选择依据写入 result.json 的 evidence_records。
