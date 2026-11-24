# 相位门规程(process gates)

六道门:`intake → 保底 partial → 逐面审查 → coverage 对账 → compose → 终审`。
每门有进入条件、退出条件与降级规则。任何门不满足退出条件时,
降级为 honest partial 交付,绝不伪造通过。

## 门 0:intake(案例接收)

- **进入**:拿到 `/input/case.json` 与 `/input/task.md`。
- **动作**:运行 `case_intake.py`,实例化 checklist.json;用 `budget_log.py` 记 intake 相位开销。
- **退出条件**:checklist.json 写出且至少 1 个审查面被识别(声明或启发式)。
- **降级**:case.json 解析失败 → 按空案例生成骨架,`intake_notes` 说明,后续人工确认审查面;
  一个面都识别不出 → 不强行编造,result.json 记 partial + uncertainty 说明。

## 门 1:保底 partial(60 秒内必须完成)

- **进入**:intake 完成。
- **动作**:确认 `/app/output/result.json` 骨架已落盘(case_intake.py 已自动写出):
  status=partial、contract 全部字段占位齐备、change_log 首条、uncertainty="审查进行中"。
- **退出条件**:result.json 存在且含 output_contract 要求的全部字段。
- **降级**:写盘失败(权限/路径) → 立即改写 `/app/work/result.json` 并在最终交付前复制;
  仍失败则在最终响应里全文打印 result.json 内容。
- **意义**:此后任何中断(超时、崩溃、预算耗尽)都留下一份合法的诚实部分结果。

## 门 2:逐面审查(主循环)

- **进入**:checklist 在手,保底 partial 已落。
- **动作**:按 facet 逐条过检查项;每条结论锚定原文逐字 quote;finding 要素齐全
  (id/type/severity/location{file,page,section,quote}/evidence/suggestion/verdict_status/category);
  面内走完后把 facet 写入 findings 文件的 `reviewed_facets`;每完成一面用 `budget_log.py` 记账。
- **退出条件**:全部 facet 走完,或预算预警触发(见降级)。
- **降级**:预算预警(`budget_log.py` 报 over_budget) → 立即停止新审查面,
  当前面收尾后直接进门 3;某面材料缺失无法审 → 该面标记待复核理由,不硬编结论。

## 门 3:coverage 对账(机械,必须执行)

- **进入**:门 2 退出(正常或降级)。
- **动作**:运行 `coverage_check.py`:生成覆盖矩阵,未覆盖 facet 如实写入 not_reviewed,
  findings 数与严重度统计写入 summary,更新 result.json。
- **退出条件**:result.json 的 status 与覆盖率一致——覆盖率 100% 才允许 complete,
  否则必须 partial(脚本硬性保证,输入声称 complete 也会被自动降级)。
- **降级**:findings 文件损坏 → 按零 findings 对账,全部面进 not_reviewed,partial 交付。

## 门 4:compose(报告合成)

- **进入**:对账完成。
- **动作**:核对每条 finding 的 quote 逐字出自材料、severity 与证据强度匹配、
  类别四选一(fact_error/insufficient_evidence/norm_issue/suggestion)归属正确;
  把待复核项与确定结论分列。
- **退出条件**:所有 finding 通过自检;not_reviewed 与 uncertainty 如实反映局限。
- **降级**:某条 finding 锚定不住 → 降级 verdict_status=待复核+理由,不删除(删除=漏报)。

## 门 5:终审(交付前最后一遍)

- **进入**:compose 完成。
- **动作**:对照 output_contract.required_fields 逐字段验收 result.json;
  跑 `budget_log.py --status` 确认总账;确认 status 诚实。
- **退出条件**:字段齐全、status 与覆盖一致、change_log 完整记录了 intake→coverage→compose 全程。
- **降级**:字段缺失 → 补齐占位并在 uncertainty 说明;时间不足 → 以对账后的 partial 交付,
  partial 必须指明局限(哪些面未审、为什么)。

## 全局降级原则

1. **先存后审**:保底 partial 永远先于一切实质性审查落盘。
2. **覆盖率对 status 有一票否决权**:<100% 永不 complete。
3. **未审面如实记账**:not_reviewed 是合法产出,静默丢面是违规。
4. **待复核优于编造**:任何指不回原文的结论标待复核,不凭空补。
