# 最小调用示例（合成示例，非正式案件结果）

本目录演示"规格账本"流水线的完整闭环。**全部输入由 make_fixture.py 现场合成，
不对应任何真实期刊或案件；expected/ 下的输出为合成示例的真实运行产物，仅示意接口。**

## 运行

```bash
python3 examples/make_fixture.py                 # 合成 template.docx / rules.txt / 两个输出件
python3 scripts/docx_spec.py examples/work/template.docx --out examples/work/template_spec.json
python3 scripts/rules_spec.py examples/work/rules.txt --out examples/work/rules_spec.json
python3 scripts/spec_merge.py examples/work/rules_spec.json:100 examples/work/template_spec.json:10 \
    --out examples/work/merged_spec.json          # 退出码 1 = 发现并裁决冲突
python3 scripts/spec_check.py examples/work/merged_spec.json examples/work/output_ok.docx \
    --json examples/work/check_fail.json --md examples/work/check_fail.md   # 退出码 1 = 有 FAIL
python3 scripts/spec_check.py examples/work/merged_spec.json examples/work/output_fixed.docx \
    --json examples/work/check_pass.json --md examples/work/check_pass.md   # 退出码 0
```

## 本示例实测结果（2026-11-24 真实运行）

- docx_spec 从合成模板抽出 24 项实测规格（A4、上下 3.17cm、单栏、
  Normal=Liberation Serif 10.5pt/1.5 倍行距、Heading1=16pt 加粗等），每项带 OOXML 溯源指针。
- rules_spec 从合成须知抽出 11 项明示规则（带行号与原文）。
- spec_merge 裁决 1 条真实冲突：须知"行距 1.25 倍"（优先级 100，采用）vs
  模板 Normal 1.5 倍（落选值完整记录在 conflicts[]）。
- spec_check 第一轮：output_ok.docx 的行距仍是 1.5 倍 → FAIL 1 项（退出码 1），
  报告精确定位 style.Normal.line_spacing；第二轮修正后 20 项 PASS、0 FAIL（退出码 0）。
- 10 项 UNKNOWN（题注措辞、参考文献著录等非机器可核对项）——按契约这些条目
  必须进入 result.json 的 manual_confirm，不得当作已通过。

expected/ 内容：merged_spec.json（含冲突裁决记录）、check_fail.json（第一轮 FAIL 证据）、
check_pass.json / check_pass.md（修正后通过证据）。
