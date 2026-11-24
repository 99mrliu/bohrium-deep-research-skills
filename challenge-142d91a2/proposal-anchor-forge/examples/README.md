# examples/ —— 合成示例（非正式案例结果）

本目录是 **合成示例**：输入材料（钙钛矿太阳能电池稳定性）为演示管线而虚构，
文献摘录中已明确标注「本示例虚构」，不代表任何真实评测案例的运行结果。

## 内容

- `input/`：合成 case.json（含 5 字段 output_contract）、task.md、
  合成前期数据 `prior_data.md`、合成文献摘录 `literature_digest.md`。
- `curated_fact_ledger.jsonl`：预制论断台账 8 条（真实运行中由 Agent 在锚定文本上
  产出）。其中故意埋入两类失真，用于演示机器拦截：
  - `C007`：quote 凭印象改写（把「衍射峰强度明显增强，提示部分分解」夸大改写为
    「大量生成……已完全分解」），归一化后不命中 → **fail**；
  - `C008`：缺 `anchor` 字段 → **unverifiable**。
- `curated_proposal_draft.md`：合成开题草稿（七要素），仅引用核验通过的论断。
- `expected/`：`run_example.sh` 真实跑出的产物，禁止手写冒充。

## 运行

```bash
bash examples/run_example.sh
```

脚本会 `rm -rf work` 后重跑：契约 init → 锚点抽取 + QC → 台账核验（演示
fail/unverifiable 拦截，退出码 1 被门控捕获）→ 以诚实 partial 收尾 result.json
（请求 ok 被强制降级为 partial，uncertainty 点名被拦截的 C007、C008）。
