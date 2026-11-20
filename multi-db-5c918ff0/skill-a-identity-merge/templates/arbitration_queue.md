# 仲裁队列（arbitration_queue.json）模板与决议规范

> dedup.py 输出的仲裁队列。Tier 3 模糊相似对**绝不自动合并**，
> 由模型逐条裁决后写入 arbitrations.json，再重跑 merge_records.py。
> 一次模型请求内批量完成全部裁决，节约请求预算。

## 队列条目（输入，脚本生成）

```json
{"pair": ["europepmc:raw_europepmc.json:2", "publisher:raw_publisher.json:3"],
 "reason_code": "T3_FUZZY_ARBITRATE",
 "evidence": {"jaccard": 0.8889, "author_overlap": 0.5,
              "year_a": 2021, "year_b": 2022, "year_diff": 1,
              "title_norm_a": "...", "title_norm_b": "...",
              "thresholds": {"jaccard": 0.6, "author_overlap": 0.5,
                             "year_window": 1}},
 "status": "pending",
 "question": "两条记录是否指向同一作品？（merge/split）"}
```

## 决议文件（输出，模型填写）/app/work/arbitrations.json

```json
[
  {"pair": ["<uidA>", "<uidB>"], "decision": "merge",
   "decided_by": "model",
   "rationale": "书面依据：为何判定同一作品（题名变体模式、作者重合、
年份差可由 online/print 解释等）"},
  {"pair": ["<uidC>", "<uidD>"], "decision": "split",
   "decided_by": "model",
   "rationale": "书面依据：为何判定不同作品"}
]
```

## 裁决纪律

1. **rationale 必填**：空 rationale 的决议无效，merge_records.py 忽略并
   由模型写入 result.json.uncertainty。
2. merge 只依据材料内证据（题名/作者/年份/容器/卷期页/摘要一致性），
   禁止臆造标识符映射补强；证据不足一律 split 并记 uncertainty。
3. 未裁决条目保持 pending：merge_records.py 标注
   `arbitration_status=pending_arbitration`，result.json status=partial
   并在 uncertainty 列出未决对。
4. 每条决议同时登记 result.json.change_records：
   `{actor: "model", action: "arbitrate", pair: [...], decision, rationale}`。
