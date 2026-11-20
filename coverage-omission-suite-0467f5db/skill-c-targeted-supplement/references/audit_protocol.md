# 审计协议（确定性复跑 + 抽检复核）

本协议规定闭环复核的执行方式，目标是让第三方仅凭本地工件即可
独立重算全部结论。

## 一、确定性复跑

1. 在 `work/replay/` 下以固定顺序重跑：
   parse_case → freeze_refset → match_coverage → supplement_engine。
2. 环境固定：`PYTHONHASHSEED=0`、`TZ=UTC`；脚本内不得使用未固定顺序的
   集合迭代、随机数或当前时间（补检账本以执行序号代替时间戳）。
3. 比对项（逐条记录于 audit_report.json 的 determinism.checks）：
   - `refset_hash`：冻结参考集内容哈希一致；
   - `initial_covered_ids` / `final_covered_ids`：覆盖集合一致；
   - `stop_rule`：触发规则一致；
   - `batches_gains`：逐批边际覆盖率收益一致。
4. 任何一项不一致 → 写入 change_log（type=determinism_mismatch），
   退出码 3，拒绝交付结论；修复后重跑至一致。

## 二、审计抽样

1. **边界命中 100% 复核**：`status=borderline` 或
   `method=title_sim` 且得分落在边界带 [threshold, threshold+band) 的
   全部命中逐条复核。
2. **干净命中确定性抽检**：其余命中按 `ref_id` 字典序排序后，
   抽取每第 5 条（索引 4, 9, 14, …，比例约 20%）。
   该规则完全确定、无需随机种子；间隔参数记录于报告的 sampling.rule。
3. **复核内容**（逐条记录于 sampling.checks）：
   - 重匹配：用相同阈值对命中对再跑一次匹配，结论须一致；
   - 证据复现：命中记录的标题或标识符须能在至少一个本地源文件
     的全文中复现（路径可核）。
4. 一致性比率 = 复核通过数 / 复核总数，写入 audit_report.json。
5. 任何分歧写入 change_log（type=audit_disagreement）：
   修正匹配明细后重跑相关阶段；未修正前 result.json 的 audit.status
   保持 review_required，不得标注为 ok。

## 三、变更记录

change_log.json 记录全部复核分歧、确定性失败与人工裁决；
result.json 引用同一变更记录，保证交付物之间的可追溯一致性。

## 四、人工复核的建议分工

- 机器复核（本协议）覆盖：确定性、重匹配一致性、证据复现。
- 人工复核建议聚焦：`标识符冲突` 类记录的裁决、
  `what_would_be_needed` 中声明的外部来源获取、
  撤稿记录的业务处置。人工裁决结果应回填至 change_log 并触发重跑。
