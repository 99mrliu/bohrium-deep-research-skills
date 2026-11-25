# 运行记录（run-record.md）— 合成示例

> **合成示例声明**：`../synthetic-input/` 全部为虚构教学数据（虚构肽 NX-3、
> 伪造 DOI `10.99977/...` 与 PMID `391xxxxx`、虚构作者与期刊），不含任何
> 真实文献实体。本目录是脚本**实际运行**的产物，非手工编写。

## 确切命令

在 `examples/` 目录下执行：

```bash
cd examples/
python3 ../scripts/screening_ledger.py run-all \
  --input synthetic-input \
  --work synthetic-output/work \
  --output synthetic-output \
  --criteria synthetic-input/criteria.json \
  --judgments synthetic-input/judgments.json \
  --borderline-decisions synthetic-input/borderline_decisions.json
echo $?   # -> 0（status=ok）
```

其中 `criteria.json` / `judgments.json` / `borderline_decisions.json` 是手工
编写的**模型步骤产物**（技能契约中由模型一次性批量完成的三步）。

## 结果概要（与数据工程设计一致）

- 识别 14 条原始记录（crossref 6 / europepmc 5 / publisher 3），去重移除 2
  （`rec-0005 ← raw-0007` DOI 精确；`rec-0012 ← raw-0014` 标题+年份+第一作者），
  规范记录 12 条。
- `prescreen` 机器排除 2 条：`rec-0003`（E1，year=2012）、`rec-0010`
  （E2，doc_type='Narrative Review'）。
- 模型判定 10 条：5 纳入、2 排除（`rec-0002` I2 人群、`rec-0007` I3 对照）、
  3 边界；边界裁定后 `rec-0004`→排除（I2）、`rec-0008`→排除（I1）、
  `rec-0011`→纳入（I4）。
- 最终流量：identified=14 → dedup=2 → screened=12 → excluded=6
  （E1:1, E2:1, I1:1, I2:2, I3:1）→ included=6，borderline_pending=0，
  三条守恒不变量全部成立，`status=ok`、退出 0。

## 负数与降级测试（实际执行，真实退出码）

| 测试 | 命令要点 | 期望/实际退出码 |
|---|---|---|
| `--help` | `screening_ledger.py --help` | 0 / 0 |
| 不同 cwd 端到端 | 在 `/tmp` 下以绝对路径跑同一 run-all | 0 / 0 |
| 重跑字节一致 | 两个全新 work/output 目录各跑一次后 `diff -r` | 无差异 / 无差异 |
| 缺 case.json | run-all 指向无 case.json 的目录 | 3 / 3（ERROR: case.json 缺失） |
| run-all 缺 --criteria | 不带 `--criteria` | 2 / 2，`result.json` 骨架保留（status=partial，uncertainty 注明原因） |
| 伪造引用 | 把 judgments[0].evidence_quote 改成记录中不存在的句子 | 3 / 3（"evidence_quote 不是记录 rec-0001 标题/摘要的逐珠子串。判定纪律禁止臆造证据"） |
| 未知标准 id | 把 judgments[0].criterion_ids 改成 ["I1","X9"] | 3 / 3（"引用了 criteria.json 中不存在的 criterion id: X9"） |
| 守恒与可追溯 | `selfcheck`（契约键/守恒/每条 exclude ≥1 标准/引用逐字核验/计数重算） | 0 / 0 |

## 确定性与诚实说明

- 材料扫描按相对路径排序、记录 id 按扫描序赋号、JSON 键排序、产物无
  时间戳/随机量——同一输入字节级可复现；`work/` 与 `result.json` 中均为
  相对产物路径，换目录重跑内容一致。
- 本合成运行的 `criteria.json` 将 `derived_needs_confirmation` 置为 `false`
  （模拟"人工已二次确认登记"）。真实运行中由模型编译的标准应置 `true`，
  此时 finalize 会如实给出 `status=partial`（退出 2）并在 uncertainty 与
  change_records 中登记确认要求——这不是失败，而是纪律。
- `borderline_queue.json` 的 `pending`/`unjudged` 非空时同样强制 partial，
  以此承接挑战要求的"遗漏说明"。
