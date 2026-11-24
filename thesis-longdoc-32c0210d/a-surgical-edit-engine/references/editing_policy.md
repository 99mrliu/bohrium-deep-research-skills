# 编辑分工策略：脚本做什么 / 模型做什么

核心原则（源自低分教训"只记账不干活"）：**凡是机械可判定的操作必须由脚本确定性完成；
模型只做非机械判断。** 每个脚本都必须能回答"它替模型省了什么"。

## 分工表

| 环节 | 执行者 | 内容 | 为什么 |
|---|---|---|---|
| 操作类型识别 | 脚本（compile） | 正则/规则识别 term_unify、float_ref_fix、replace、delete、format_normalize | 机械可判定；模型识别慢且不一致 |
| target 章节解析 | 脚本 | "全部章节"→文件列表；"第X章"→文件名/标题匹配 | 机械可判定 |
| 图表悬空引用扫描 | 脚本 | 题注集合 vs 正文引用集合的差集 | 纯集合运算，模型逐行查会漏 |
| 机械替换落改 | 脚本（apply） | 字面替换、编号改号、单位空格、删除 | 零创造；模型改长文易引入二次错误 |
| hunk 级留痕 | 脚本 | change_log.json：file/op_id/before/after/line_range | 模型留痕浪费 token 且格式漂移 |
| 快照与回滚 | 脚本 | apply 前快照 .snapshot，--rollback 恢复 | 事务语义必须确定性 |
| 验收断言生成 | 脚本（verify） | 缺失/存在断言 + 图表引用完整性 | acceptance 的机械部分可自动判定 |
| 契约装配交付 | 脚本（make_result） | 运行时读 output_contract.fields 逐字段填充、原子写 | 契约对齐不能靠模型记忆 |
| 非机械改写 | **模型** | `manual` op：语义重写、候选不唯一的引用判断、未入规则表的格式规范、paraphrase | 需要语言理解，脚本做会误改 |
| manual 完成度确认 | 模型 + 脚本 | 模型改完章节后重跑 verify，让脚本判定 | 判定仍归脚本 |

## 模型行为红线

1. 不手工执行已被脚本覆盖的机械编辑（重复劳动且破坏 change_log 的一致性）。
2. 不修改 ops.json 中确定性 op 的 params；有异议时在 result 的 uncertainty 中说明。
3. 不改 verify 报告充 PASS；FAIL 要么修复重验，要么诚实 partial。
4. 编辑工作副本时只动 manual op 涉及的段落，保持其余字节不变（保护 hunk 可审计性）。

## 异常矩阵（与 SKILL.md §5 一致，此处为判定细节）

| 异常 | 检测点 | 处理 | 对 status 的影响 |
|---|---|---|---|
| 章节目录缺失/空 | compile 启动 | 直接非零退出；make_result 写 failed | failed |
| item 无法识别 | compile classify | op.type=manual + reason | 不变（manual 计 uncertainty→partial） |
| target 匹配失败 | compile resolve | 回退全部章节 + op.warning | 不变 |
| 锚点零命中 | apply 各 handler | problem 记录、跳过该 op、其余继续 | partial |
| 目标文件缺失 | apply 各 handler | problem 记录、跳过该文件 | partial |
| 引用候选不唯一 | compile float_ref_fix | params.unresolved；verify SKIP；模型判断 | partial（未解决时） |
| acceptance FAIL | verify | 退出码 1；逐项列出 file:line | partial（未修复时） |
| change_log/acceptance 缺失 | make_result | problems 记录，字段填 null | failed/partial |
| 未知 contract 字段 | make_result | 填 null + problems | partial |
| 回滚请求 | apply --rollback | 恢复 .snapshot，change_log 记 rollback | 不变 |

## "先存 partial 再改进"协议

apply 完成后**立即**跑一次 make_result（此时 manual 项必然导致 status=partial），
把可用成果落盘 `/app/output/result.json`；随后模型处理 manual、重跑 verify、
再跑 make_result 覆盖。任何时刻超时，/app/output 里都存在一份诚实标注的最新成果。
