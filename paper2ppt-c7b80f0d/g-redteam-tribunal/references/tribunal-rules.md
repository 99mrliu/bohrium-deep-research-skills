# 台账规则与两轮收敛协议

## 状态机

```
            redteam_scan 检出
                  │
                  ▼
                open ──── tribunal_log --fix ───────► fixed
                  │
                  └──── tribunal_log --disposition ─► dispositioned
                        (accept-risk | reject + 理由)
```

- 仅 `open` 可迁移；`fixed` / `dispositioned` 为终态（撤销只能新增条目，不改历史）。
- 禁止物理删除条目。重复入账幂等（同 id 不重置状态）。
- 每次操作追加 history：{seq, action, actor, note}；actor 记录操作者
  （redteam_scan / apply_fixes / agent）。

## disposition 的合法理由

- **accept-risk**：缺陷真实存在但影响可接受，理由必须说明
  (a) 风险边界（影响哪页哪个论断）；(b) 为什么当前轮不修（如启发式误报、
  素材限制、受众可容忍）。
  例：R8 —「Figure 1 caption 含 schematic 关键词，但该图同时承载唯一主数据曲线，
  保留引用；风险限于读者可能低估其证据权重」。
- **reject**：finding 为检测器误报，理由必须给出反证
  （如事实池确实存在该锚点，指出 facts.json 中的位置）。
- 空理由 / 无 --reason 的 disposition 是非法操作，`tribunal_log.py` 拒绝执行。

## 两轮收敛协议

1. **Round 1（全量）**：对 deck v1 跑 R1–R8，全部入账。
2. **处置**：机器可修（R1/R2）由 `apply_fixes.py` 自动修并回写台账；
   其余由 Agent 修改 deck 后 `--fix` 销账，或 `--disposition` 正式裁决。
3. **Round 2（全量复扫）**：对修复后的 deck v2 再跑 R1–R8。
4. **门禁**（`converge_gate.py`）同时满足才 verdict=pass：
   - 台账中无 open 的 error；
   - Round 2 无新增 error（rule+slide+evidence 键在 Round 1 不存在）。
   warn 不阻塞，但 remaining_warns 全量列入 convergence.json。
5. **不达标**：按 references/budget-protocol.md 决定是否 Round 3（定向复扫）
   或报 partial，禁止在 verdict=fail 时声称 success。

## 与 result.json 的衔接

- `compliance_checks` 必须含 `redteam_converged`：expected="pass"，
  actual 取自 convergence.json 的 verdict（真实测量，禁止断言）。
- `change_records` 从台账 fixed/dispositioned 条目生成，含 rollback 说明。
