# 人工复核工作流：从 review.html 勾核到 overrides 回写

本技能的立场：**机器筛查只到 borderline 为止，最终处置由人勾核**。
build_review.py 生成的不是"答案"，而是一套供人复核的交付物。本文件规定
人工复核的标准动作与回写格式，Agent 扮演复核者时同样照此执行。

## 复核顺序（先粗后细，每步都有对应交付物）

1. **看 flow.svg**：先核对计数是否自洽（识别 = 去重后 + 重复；
   去重后 = 纳入 + 待复核 + 排除）。计数不自洽说明管线出错，不要继续逐条复核，
   先修管线。check_exports.py 的 X5 已自动做这一步，但人眼扫一眼成本为零。
2. **看 report.md 第四、六节**：排除理由分布是否合理？不确定性清单里的
   每一项（缺失清单文献、冲突意见夹具、borderline 条数）是否都能接受？
3. **开 review.html 逐条目检**：重点只有两类行——
   - `待复核`（borderline，琥珀色）：机器证据不足，必须人判；
   - 带红色"夹具"徽标的行：输入夹具标记（synthetic_duplicate /
     conflict_opinion 等）。夹具是**输入事实**：登记它的去向，不替冲突意见
     做学术裁决。
4. **勾核翻转**：勾选需要推翻机器处置的行。勾选语义：
   - `include` → 翻转为 `exclude`；
   - `exclude` → 翻转为 `include`；
   - `borderline` → 翻转为 `include`（若判为排除，保持不勾并在备注说明）；
   - `duplicate` 行**锁定不可勾**：重复是输入事实，如需恢复请处理源数据。
5. **生成并回写 overrides.json**：点击"生成 overrides.json"，把文本框内容
   保存为 `/app/work/overrides.json`，**把 note 改成具体理由**（一句话，可问责），
   然后重跑：

   ```bash
   python3 SKILL_DIR/scripts/build_review.py --case /input/case.json \
       --input-dir /input --work /app/work --out /app/output \
       --overrides /app/work/overrides.json
   python3 SKILL_DIR/scripts/check_exports.py --case /input/case.json --out /app/output
   ```

   重跑后被翻转的行在 ledger.csv 的 review 列标 `✓人工`，reason 追加
   `manual_override(was:...)`，note 记录人工理由——机器原始判断永久留痕。

## overrides.json 格式

```json
[{"rid": "R06", "decision": "include", "note": "摘要确认涉及钠离子电池日历老化，与稳定性主题相关"}]
```

- `rid` 必须与 ledger.csv / review.html 中的 rid 一致；未知 rid 被静默忽略
  （report 不变），所以保存后务必重跑并核对计数变化。
- `decision` 仅接受 `include` / `exclude` / `borderline`。
- 解析失败的 overrides 会被忽略并在 uncertainty 中声明，不会静默生效。

## 判不准怎么办

保持 borderline 并在 uncertainty 中说明，**不要猜**。partial 是体面且常见的
终态：列出的保留项之外的部分完整可信，复核者可以只针对保留项继续工作。
check_exports.py 不惩罚 partial，只惩罚不一致。

## 复核完成的标准

- check_exports.py 输出 PASS（exit 0）；
- uncertainty 中不再有"borderline 待勾核"项（要么已勾核，要么书面说明保持
  borderline 的理由）；
- 渲染预览（见 SKILL.md"渲染预览"一节）目检无异常。
