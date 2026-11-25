# termbase.json 结构约定（Bundle A）

```json
{
  "version": 1,
  "terms": {
    "<english term>": {
      "abbr": "GB | null",
      "kind": "defined-term | abbreviation | capitalized-multiword | hyphenated-compound | manual",
      "occurrences": 3,
      "rank": 1,
      "forbid": ["禁用变体1", "禁用变体2"],
      "decision": {
        "kind": "preferred | keep_original",
        "target": "晶界 或原词",
        "sense": "义项备注（材料晶粒界面）",
        "reason": "决议依据",
        "decided_by": "agent",
        "decided_at": "ISO-8601Z"
      }
    }
  },
  "lock": {"sha256": "决议规范化JSON的sha256", "terms_locked": 7, "locked_at": "…"},
  "history": [{"event": "decide", "term": "…", "decision": {…}, "after_lock": false}]
}
```

## 规则

1. `lock.sha256 = sha256(json.dumps({term: decision}, sort_keys=True, ensure_ascii=False))`。锁定后任何 `decide` 都必须 `--force` 并留下 history 记录，之后必须重新 `lock`。
2. `keep_original` 是合法决议（公式、专名、文献编号），审计认可其零译名。
3. `forbid` 列表在决议时给出常见错误译名；审计对其出现零容忍（可安全回填）。
4. 决议缺失（decision=null）的候选不参与审计，但必须由 Agent 在翻译前处理或显式声明放弃。
