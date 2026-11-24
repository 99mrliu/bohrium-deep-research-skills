# 诚实契约：人工确认环节的不可逾越线

1. **模型建议 ≠ 人工复核**。队列内记录在 merge_review.py 收到真实人工
   决定前，`final_label` 必须为 null，`confirmation_status` 保持
   `pending_human_confirmation`。任何"模拟人工""代填决定"都是伪造。

2. **未完成要喊出来**。存在 unresolved（队列中无人工决定）或 rejected
   （人工决定行未过校验）时，merge_review.py exit 3，result.json
   status 至多 partial，并在 uncertainty 点名缺失的记录与原因。

3. **推翻必须留理由**（V4）。人工决定与模型建议不一致时 rationale
   必填——这正是事后回答"为什么这篇被排除"的依据。一致时 rationale
   可空，因为模型侧已有理由码与证据片段。

4. **回填来源必须真实**。human_decisions.csv 由研究者填写；在平台
   评测中若无真实人工输入，正确做法是：保留队列原样交付、status 记
   partial、uncertainty 声明"人工复核未执行"，**而不是**用模型生成
   一张假的 CSV。

5. **override_rate 要说人话**。confirmation_ledger.json 的
   confirmed/overridden/override_rate 如实呈现人机分歧规模；
   高推翻率提示模型判定口径需要修正，禁止为显得"一致"而筛选回填。

6. **队列外也有账**。自动放行的记录带
   `confirmation_status=auto_accepted_below_gate`，说明它们没经过
   人工确认、以及为什么（未命中触发器）。
