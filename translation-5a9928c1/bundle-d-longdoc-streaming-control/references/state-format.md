# state.json 结构（Bundle D）

```json
{
  "version": 1,
  "plan_sha256": "…",
  "budget": {"requests_used": 4, "seconds_used": 100.0,
             "requests_limit": 64, "seconds_limit": 900},
  "chunks": {
    "c001": {"status": "done | pending | failed",
             "unit_hashes": {"u0001": "…"},
             "translation_sha256": "…",
             "completed_at": "ISO-8601Z"}
  }
}
```

## 状态机

pending → done（mark-done 校验通过）/ failed（人工标记或反复失败）；
done → done（幂等同内容跳过）。无删除路径：撤销必须新建 job。

## mark-done 硬性校验

1. 块内**全部**单元都有非空译文；
2. 每个单元的 `source` 与 plan 中记录的 sha256 一致（防源文改动后续译）。

任一失败 exit 1 并逐条列出原因。
