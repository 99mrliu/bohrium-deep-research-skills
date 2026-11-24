# contract-first-budget-orchestrator

文献综述生成的"过程质量控制 / 资源调度"Skill：契约先行——先把 output_contract
逐字段解析为产出计划并立即写出 status=in_progress 的 partial result.json；
预算编排——按文献数与研究问题相关度把 64 次模型请求分配到各阶段，裁定每篇文献的
阅读深度（全文/章节/摘要降级阶梯），预留校验修复保底；断点续跑——state.json 账本 +
一致性校验（阶段-产物一致性、契约字段完备、change_log 覆盖）支持中断恢复。

- 入口说明：`SKILL.md`
- 运行：`python3 scripts/run_case.py init|check|finalize …`（详见 SKILL.md 第 4 节）
- 账本：`python3 scripts/budget_ledger.py status --work /app/work`
- 合成示例：`python3 examples/make_example.py /tmp/cfo-demo`（详见 `examples/README.md`）
- 依赖：Python 3 标准库；有 `pdftotext` 时自动用于 PDF，缺失时纯文本材料仍可运行。
