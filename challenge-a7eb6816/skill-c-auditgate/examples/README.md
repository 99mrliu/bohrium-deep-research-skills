# 合成示例（非正式案例结果）

> ⚠ 本目录为**虚构的合成示例**，用于演示审计门流程，**不是**任何正式评测
> 案例的结果。「某锂电池回收研究」全文为虚构，数据无实际来源。

## 材料

- `source.md`：虚构源文，9 句，含浸出率（96.5%/94.2%）、减排 40%、
  成本 3200 元/吨、图 2 引用等关键信息。
- `draft.md`：虚构改写稿（新闻风格），7 句；**删去了两处关键信息**：
  浸出渣金属残留率（源文 S4）与图 2 引用（源文 S8）；并将「3 家」概括
  为「多家」。
- `edit_log_bad.jsonl`：问题清单——第 1 条 `reason` 为空；删去图 2 引用
  （S8）却无 `omit` 记录。
- `edit_log_good.jsonl`：合规清单——每处删改有 action 与理由，S4/S8 均有
  `omit` 记录，2 条 `needs_confirmation` 待确认。

## 真实运行命令与结果

在 bundle 根目录执行（`$SK` 指 bundle 根）：

```bash
python3 scripts/align_map.py examples/source.md examples/draft.md -o examples/expected
# 退出码 0；draft=7 句 source=9 句，uncovered_key=2（S4、S8），mode=normal

python3 scripts/editlog_check.py examples/edit_log_bad.jsonl \
    --alignment examples/expected/alignment.json \
    -o examples/expected --prefix editlog_report_bad
# 退出码 4（FAIL）：检出 1 条 bad_reason（第 1 行空 reason）
# + 1 条 omit_not_logged（S8 图 2 引用删减无记录）

python3 scripts/editlog_check.py examples/edit_log_good.jsonl \
    --alignment examples/expected/alignment.json \
    -o examples/expected --prefix editlog_report_good
# 退出码 0（PASS）：9 条全合法，2 条待确认，删减均有记录

python3 scripts/audit_gate.py --alignment examples/expected/alignment.json \
    --editlog-report examples/expected/editlog_report_bad.json \
    --source examples/source.md --draft examples/draft.md \
    -o examples/expected --prefix gate_verdict_fail
# 退出码 5（FAIL）：editlog_legal 与 key_source_coverage 两项 FAIL，不过门

python3 scripts/audit_gate.py --alignment examples/expected/alignment.json \
    --editlog-report examples/expected/editlog_report_good.json \
    --source examples/source.md --draft examples/draft.md \
    -o examples/expected --prefix gate_verdict_pass
# 退出码 0（PASS）：四项检查全过，可交付
```

以上输出即为 `expected/` 下的真实文件（未手工修改）。

## expected/ 文件说明

| 文件 | 内容 |
|---|---|
| `alignment.json` / `alignment.md` | 双向对齐：7 句稿全部 supported/weak，最佳源句映射全部正确；未覆盖关键源句 = S4、S8 |
| `editlog_report_bad.json/md` | FAIL：bad_reason（第 1 行）+ omit_not_logged（S8） |
| `editlog_report_good.json/md` | PASS：9 条合法，2 条待确认（S7-D6 概括表述、S4 删除） |
| `gate_verdict_fail.json/md` | FAIL（退出码 5），不过门不交付 |
| `gate_verdict_pass.json/md` | PASS（退出码 0），附 2 条待确认问题交原作者 |

## 调参记录（真实）

初版示例中 Markdown 标题行被当作普通句参与对齐，导致句序号错位、
标题互相干扰（标题对得分 0.175）。修复：`align_map.py` 分句前剔除标题行，
重跑后 7 句稿的最佳源句映射全部正确，稿句平均最佳分 0.5083。
默认阈值（supported 0.35 / weak 0.15）未改动：意译程度较高的两句
（D3→S3 得分 0.3438、D6→S7 得分 0.2258）落 weak 档，属协议内预期行为，
不影响 PASS；反向覆盖以 weak 阈值判定，S4/S8 均稳定未覆盖（最高分 0.0714）。
