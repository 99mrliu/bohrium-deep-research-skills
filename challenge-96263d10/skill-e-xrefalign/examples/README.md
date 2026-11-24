# 最小调用示例（合成示例，非正式案件结果）

**manuscript.md 由 make_fixture.py 现场合成，内置四类真实缺陷；
expected/ 下为合成示例的真实运行产物，仅示意接口。**

## 运行

```bash
python3 examples/make_fixture.py
python3 scripts/xref_scan.py examples/work/manuscript.md --out examples/work/xref_bad.json     # 退出码 1
python3 scripts/refstyle_check.py examples/work/manuscript.md --out examples/work/refs_bad.json # 退出码 1
python3 scripts/renumber_plan.py examples/work/xref_bad.json --out examples/work/plan.json
# （Agent 按 plan 修正后得到 fixed.md）
python3 scripts/xref_scan.py examples/work/fixed.md --out examples/work/xref_fixed.json         # 退出码 0
python3 scripts/refstyle_check.py examples/work/fixed.md --out examples/work/refs_fixed.json    # 退出码 0
```

## 本示例实测结果（2026-11-24 真实运行）

原稿四项缺陷全部被机器捕获并定位：

- `dangling_reference` ERROR：正文引用"图2"，但第二图题注误标"图3"（块 4/块 6）。
- `caption_position` ERROR：表1 题注在表下方（规则：表题注在表上方）。
- `numbering_gap` / `unreferenced_caption` WARNING：图编号 1,3 断档、图3 无正文引用。
- 参考文献：[3] 缺年份 ERROR；[2] 缺类型标志 + 4 作者未截断 + 缺句点 WARNING。

renumber_plan 给出映射 {3→2}、题注修改点（块 6）、以及必须人工裁定的
悬空引用点（块 4 的"图2"——改完题注后自动消解）。按方案修正后的 fixed.md：
xref_scan 0 ERROR 0 WARNING；refstyle_check 3 条全 PASS（退出码均为 0）。

expected/ 内容：xref_bad.json、refs_bad.json、plan.json、xref_fixed.json、refs_fixed.json。
