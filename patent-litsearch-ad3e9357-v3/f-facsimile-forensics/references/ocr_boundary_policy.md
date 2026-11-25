# OCR 边界与容差声明策略（ocr_boundary_policy.md）

## 1. 原则：先声明，后匹配

任何非逐字（non-verbatim）匹配都必须事先在策略 JSON 中声明。`page_anchor.py` 与
`facsimile_discrepancy.py` 只执行策略允许的容差；未声明的容差命中会被**拒绝**
（退出码 1，stderr 给出明确原因），而不是被静默使用。

## 2. 策略 JSON 模式

```json
{
  "allow_whitespace_collapse": true,
  "allow_page_boundary_merge": true,
  "declared_boundaries": [
    {"record": "FX1001", "field": "related_wo",
     "note": "WO 2099/054321 A1 文本跨 OCR 页边界（第 2 页 -> 第 3 页）合并；合并保留并在此声明，不做静默重拆。"}
  ]
}
```

- `allow_whitespace_collapse`：允许把任意空白串折叠为单个空格后匹配
  （典型场景：一条事实被 OCR 断成两行）。锚点记 `match_type = "whitespace_collapsed"`，
  `quote` 保留原始文本（含换行）。
- `allow_page_boundary_merge`：允许在按页拼接（`\n` 连接）的文本上匹配跨页事实。
  锚点记 `page = "N-M"`、`match_type = "page_boundary_merged"`，
  `byte_span_basis = "joined_pages_text_utf8"`。
- `declared_boundaries`：对每一处已知的 OCR 合并边界做人类可读登记。
  该数组是**声明性档案**，脚本不据此放松匹配（放松只由上面两个布尔量控制），
  但其内容必须被保留并汇入最终结果的 OCR 边界声明字段。

## 3. WO 合并边界的保留义务

当某条 WO 记录的文本系跨 OCR 页边界合并而来（评测案例中明确要求保留此类边界）：

1. 不得把合并文本静默拆回两页、也不得当作两页各自独立的事实记录；
2. 锚定该事实时使用策略允许的容差，锚点本身即携带 `page = "N-M"` 与
   `match_type` 痕迹；
3. 在 `/app/output/result.json` 中把 `declared_boundaries` 的对应条目汇入
   OCR 边界声明字段；若案例未提供策略文件，则在 `uncertainty` 中如实写明
   "该合并边界系观察所得，未有官方策略文件声明"。

## 4. 拒绝语义

- 值只在折叠空白后可匹配而策略未声明 → 退出码 1：
  `REFUSED: value ... matches only with whitespace collapsing ... but the policy does not declare allow_whitespace_collapse`
- 值只在跨页拼接后可匹配而策略未声明 → 退出码 1：
  `REFUSED: value ... matches only across a page boundary ... but the policy does not declare allow_page_boundary_merge`
- 两种容差都声明时，脚本还支持复合匹配
  `match_type = "page_boundary_merged+whitespace_collapsed"`。

## 5. 审计留痕

每次 `locate` 输出都含 `policy_applied` 快照（两个布尔量的实际取值），
差异台账同样携带该快照，保证事后可审计"当时允许了哪些容差"。
