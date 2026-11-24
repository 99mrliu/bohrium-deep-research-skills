# 合成示例（SYNTHETIC EXAMPLE）

本示例为**合成演示**，所有文献与研究问题均为虚构，不冒充正式案例结果。

## 运行

```bash
python3 examples/make_example.py /tmp/arf-demo
```

## 演示内容

- 4 篇虚构短文：D1 全文、D2 全文（结论与 D1 冲突）、D3 仅摘要、D4 是 D1 的换题近重复。
- `run_case.py init` 真实执行：防御式解析、分级、近重复分组（D4 与 D1 成组）。
- 模拟模型阶段产物（标注 simulated；摘录由脚本从 `pages/*.jsonl` 程序化抽取保证逐字）。
  草稿故意埋入两处问题：
  1. 一句引用不存在的 `[E99]` 的论断 —— 第一次 `render` 时 `link_check.py`
     **非零退出**并打印 `unresolved_markers`；
  2. 一句无证据标记的实质句 —— 作为警告（不阻断）列入报告与审计 HTML。
- 脚本自动修复草稿（删去坏引用句），重跑 `render` 通过，再跑 `finalize`：
  `build_result.py` 镜像 output_contract 全字段，`validate_result.py` 手写 schema 校验通过。

## 查看点

- `/tmp/arf-demo/output/audit_report.html`：浏览器直接打开；论断句中的 `[E#]` 可点击
  跳转至证据明细（逐字摘录 + 页锚点）；含未覆盖文档（D4）与无标记句公示。
- `/tmp/arf-demo/output/evidence_matrix.csv`：Excel 直接打开（UTF-8 带 BOM）。
- `/tmp/arf-demo/output/coverage_map.json`：文档×主题矩阵 + `uncovered_documents`。
- `/tmp/arf-demo/output/link_check_report.json` / `validation_report.json`：两道闸口结果。
- `/tmp/arf-demo/output/result.json`：终版结构化结果（含 output_contract 全部字段）。
