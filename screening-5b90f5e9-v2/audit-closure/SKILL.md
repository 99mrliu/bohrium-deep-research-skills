---
name: screening-audit-closure
description: 系统性文献筛选的流程审计与计数闭合门禁。当案例要求筛选全流程可独立复核（各环节条目数首尾闭合、谁在哪一步做了什么有记录、同批题录重跑结果一致）时使用。重心在过程质量控制：分阶段计数台账、PRISMA 链闭合硬门（C1–C4）、产物 sha256 指纹、复跑语义级 diff。不判断单条记录对错、不替代证据锚定、不伪造一致性——复跑不一致时如实报告并阻断交付。
---

# screening-audit-closure — 流程审计·计数闭合·复跑确定性

把"各环节计数能否首尾对上、产物能否证明没被事后改动、重跑能否复现"
三件事做成自动硬门。本技能不评判单条判定的对错，它保证整条流程
**可以被第三人独立复核**。

## 1 适用场景与红线

**适用**：案例要求筛选流程可复跑、计数闭合、审计链完整；需要对比
两次运行是否一致；需要交付产物指纹供复核。

**红线**：
- 不凑数：闭合 FAIL 时禁止回头改早期计数，只能查明差额并补更正记录；
- 不藏差额：未判定记录必须显式记 unprocessed 并点名，禁止用它吸收差异；
- 不伪造一致性：rerun_diff 报非确定时如实写入 uncertainty，禁止掩盖；
- 台账只经脚本写入：手改台账会被闭合规则或 manifest 抓住。

## 2 运行环境

- Python 3 标准库，无第三方依赖；脚本在 `$SKILL/scripts/`；
- 退出码：0=正常/PASS；2=输入缺失；3=闭合 FAIL / 产物被改 / 复跑非确定；
- 台账时间戳默认取当前 UTC；需要逐字节复现时用 `--timestamp` 固定。

## 3 端到端运行契约（平台案例）

1. 读 `/input/case.json` 与 `/input/task.md`，确认 case_id、材料、
   output_contract 字段。
2. **尽早**落 `/app/output/result.json` 骨架（status=in_progress），逐步填充。
3. 筛选流程的**每个阶段完成后立即** `stage_ledger.py record`，不留到收尾补账；
   阶段包括：identified（材料记录总数）、dedup、screened、included、
   excluded、needs_human（以及必要的 unprocessed）。
4. 交付前依次过三道门：closure validate（C1–C4）→ rerun_diff（若有两次
   运行）→ manifest create。任何一道 exit 3 都不得声称 completed。
5. result.json 填齐全部合同字段；status ∈ completed/partial/failed；
   partial 写明哪道门未过、差额多少、受影响记录。

## 4 审计管线（编号步骤）

0. **[脚本] 建账**：每阶段结束即
   `stage_ledger.py --ledger /app/work/audit/audit_ledger.json record
   --stage <阶段> --input-count N --output-count M --operator <system|model|human:...>
   --basis <产物路径> --notes <一句依据>`
1. **[脚本] 闭合校验**：`stage_ledger.py --ledger ... validate --out .../closure_report.json`
   → C1–C4。FAIL 按差额排查（规则见 references/closure_rules.md），
   修复后重跑到 PASS。
2. **[脚本] 流量摘要**：`stage_ledger.py --ledger ... summary --out .../audit_summary.json`
   → PRISMA 风格流量表，供 result.json 的 counts 字段引用。
3. **[脚本] 复跑对比（条件触发）**：同一批题录的两次判定
   `rerun_diff.py --a run1.json --b run2.json --out .../rerun_report.json`。
   NONDETERMINISTIC（exit 3）按 references/determinism.md 流程排查。
4. **[脚本] 产物指纹**：`manifest.py --dir /app/output create`；
   复核方 `manifest.py --dir /app/output verify`。
5. **[模型] 汇总**：把 closure_report、audit_summary、rerun_report 的
   关键数字填入 result.json 相应字段，uncertainty 点名全部未闭合项。

## 5 输出合同映射（常见字段）

| 合同字段 | 来源产物 |
|---|---|
| case_id | case.json |
| status | 三道门全过 → completed；任一未过 → partial 并点名 |
| product | audit_ledger.json + audit_summary.json（全流程计数与操作记录） |
| evidence_matrix | closure_report.json 各检查项算式与差额 |
| sources | 台账 basis 字段指向的产物清单 |
| uncertainty | 未闭合差额、unprocessed 记录、复跑 flips 清单 |
| change_records | 台账中同阶段多条记录即变更轨迹；更正记录说明 |
| counts | audit_summary 的 PRISMA 流量 |
| checks | closure overall / rerun deterministic / manifest verify 状态 |

## 6 异常处理表

| 异常 | 处理 |
|---|---|
| 材料记录总数无法确定 | identified 阶段记材料盘点值并在 notes 说明口径；仍不可知则 partial |
| C1/C2 差额非零 | 按差额回查对应阶段产物；补更正记录；无法查明则 partial 并给差额 |
| 复跑 NONDETERMINISTIC | 按 determinism.md 四步排查；修复重跑；无法消除则 partial+flips 清单 |
| manifest verify FAIL | 产物被改动：重新生成受影响产物，重跑其下游校验 |
| 案例只有单次运行 | rerun_diff 跳过并在 uncertainty 声明"未做复跑验证" |
| 预算耗尽有未判记录 | 记 unprocessed 阶段，C2 仍闭合，status=partial 并点名数量 |

## 7 最小调用示例（合成数据）

```bash
cd <bundle 根目录>
python3 scripts/run_example.py
```

演示（全部**合成**数据）：正确台账（200→23 去重→177→12+160+5）validate
PASS；篡改台账 excluded 160→159 后 C2 FAIL exit 3（临时副本）；manifest
create/verify PASS 且篡改产物后 verify FAIL exit 3（临时副本）；
rerun_diff 对一处标签翻转报 NONDETERMINISTIC exit 3，对同内容乱序文件报
DETERMINISTIC。最终打印 `EXAMPLE PASS`。产物在
`examples/minimal/output/`，详见 `examples/minimal/RUNLOG.md`。

## 8 自查方法

- 重跑 run_example.py，closure/verify/rerun 各结论与 RUNLOG 一致；
- 手工重数任一 basis 指向的产物，与台账计数一致；
- 确认 closure_report 每条 FAIL 都有算式与差额，不是空结论；
- 确认 manifest.json 覆盖 /app/output 全部交付文件且 verify PASS。
