# runbook.md — T0–T900 分钟级运行手册（budget-runbook-qc）

硬预算：900 秒 / 64 次模型请求 / 单次响应 16384 token。
本手册把预算当成显式调度对象：**每步先查水位（budget_ledger.py status），再决定做什么。**

## 1. 阶段表（默认 900s/64 请求）

| 阶段 | 时间窗 | 请求配额 | 动作 | 退出条件 |
|-|-|-|-|-|
| P0 开工 | T0–T30 | 0–2 | budget init → 读 case.json/workorder/章节清单 → **checkpoint init 立即写 partial result.json** → 把章节复制到 /app/work/chapters | partial 骨架落盘 |
| P1 规划 | T30–T60 | 1–3 | qc_gates run 先跑一遍基线（未编辑时的 FAIL 清单＝真实工作量）→ 按 §3 规则裁剪工单 → 把计划写进 change_record 草稿 | 裁剪方案确定 |
| P2 执行循环 | T60–T600 | ≤40 | 逐 item：机械编辑（sed/python，非模型逐字改）→ tick → qc_gates run（单 item 重验）→ promote 对应字段。**每个 item 结束都必须让 result.json 比上一刻更完整** | 必做项全 PASS 或水位触发 |
| P3 打磨 | T600–T780 | ≤14 | 可选项、manual 门批量判定（一次响应判多个 manual 门）、consistency_report 补全 | 水位正常才允许进入 |
| P4 收尾 | T780–T900 | ≤7 | assemble → promote uncertainty/sources → qc_gates run 终验 → checkpoint finalize → checkpoint validate → （预算宽裕时）fault_inject run | result.json status=complete 或诚实 partial |

**红线：无论进行到哪，T780 必须进入 P4。P4 的一切动作都不依赖模型请求也能完成大半。**

## 2. 水位触发动作表

水位 = max(已用秒/900, 已用请求/64)，由 budget_ledger.py 每次 tick 后自动打印。

| 水位 | 区间 | 触发动作 |
|-|-|-|
| normal | 0–70% | 按阶段表推进；允许重跑一次失败的门；允许打磨项 |
| tight | 70–85% | 只做必做项：砍 P3 全部可选打磨；manual 门一次性批量判定（1 次请求判完所有 manual 门）；不再重跑全文 grep，只重验刚改的 item |
| floor | >85% | 立即停手：不再编辑章节；promote 已完成成果；把未完成 item 逐个写进 problems 字段（`problems=["item N 未完成: 原因"]`）；uncertainty 写明限制；qc_gates run 终验；finalize 成功则 complete，失败则**保持 partial 直接交付** |

floor 水位下的交付优先级：**result.json 字段齐全且诚实 > 章节全部改完**。
一个 status=partial 但字段诚实填写的 result.json 远好过一个改完章节却没写 result.json 的运行（后者零分）。

## 3. 工单规模裁剪规则

| 工单规模 | normal 水位 | tight 水位 | floor 水位 |
|-|-|-|-|
| 3 项 | 全做，P2 每项 ~3 请求 | 全做，跳过重验只跑终验 | 只保证 result.json 完整 |
| 5 项 | 全做；第 4–5 项若是打磨类可降级 | 砍第 5 项及标记"可选"的项，写入 problems | 只完成已开工的 item + result.json |
| 10 项 | 分 3 批（P0 可机械编译的优先，约 3/3/4），每批结束跑 qc_gates | 只做第一批 P0 + 已在改的 item；其余整批写 problems | 立即收尾，未开工 item 全部写 problems |

分批原则：
1. **可编译门优先**（absent/present/figure_ref_integrity）——机械可判，单位请求收益最高。
2. **manual 门聚批**——所有 manual 门攒到一次模型响应里集中判定，每条必须有 reason。
3. **互相依赖的 item 同批**（如"术语统一"会影响"引文一致性"的判定）。

## 4. 每步固定仪式（不可省略）

```
python3 /skills/weekly-skill/scripts/budget_ledger.py status --workdir /app/work   # 先查水位
# ... 做本步工作（编辑/判定）...
python3 /skills/weekly-skill/scripts/budget_ledger.py tick --workdir /app/work --request --seconds <本步秒数> --note "<一句话>"
python3 /skills/weekly-skill/scripts/checkpoint.py promote --workdir /app/work --outdir /app/output --field '<字段>=<值>'
```

tick 的 --seconds 必须诚实自报；ledger 不连真实时钟，预算纪律靠诚实记账维持。
