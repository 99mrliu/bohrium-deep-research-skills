# source-truth-gate

文献综述生成的"上游来源真实性门控"Skill：先做来源取证与身份核验（题名/年份/DOI 比对、
近重复裁定、撤稿标记、T1/T2/T3 信任分层），再进行筛选、主题归纳、证据组织与草稿生成；
交付前由脚本执行引用门控与信任强制，未通过的论断自动降级。

- 入口说明：`SKILL.md`
- 运行：`python3 scripts/run_case.py init|verify|finalize …`（详见 SKILL.md 第 4 节）
- 合成示例：`python3 examples/make_example.py /tmp/stg-demo`（详见 `examples/README.md`）
- 依赖：Python 3 标准库；有 `pdftotext` 时自动用于 PDF，缺失时纯文本材料仍可运行。
