# 审计门判定（gate verdict）

## 总判定：**FAIL**（退出码 5）

## 检查项

| 检查 | 判定 | 说明 |
|---|---|---|
| unsupported_draft_sentences | ✅ PASS | unsupported 稿句 0 条，均已列入待确认 |
| key_source_coverage | ❌ FAIL | 1 条关键源句被删减但无合法记录：S8 |
| editlog_legal | ❌ FAIL | editlog_check 判定 FAIL，错误 2 条 |
| numeric_anchors | ✅ PASS | 稿件数字 9 个全部在源文中字面出现 |

## 待确认问题（随交付一并提交原作者）

- 无

---
PASS=可交付；FAIL=不过门不得交付；MANUAL_REVIEW=降级为人工复核清单。
