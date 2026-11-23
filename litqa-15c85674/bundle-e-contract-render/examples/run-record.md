# 最小调用示例运行记录（合成示例，非正式案例结果）

> 输入 `synthetic-case.json` 为虚构论文（SYN-2026-Alloy-08，ECAP 铝合金，5 个段落、
> 2 个中文问题），**含 9 字段 output_contract**（基线 6 字段 + `sources` /
> `uncertainty` / `change_log`），用于演示契约提取与 extra_fields 并入。
> 以下命令均真实执行。

## 命令序列

```bash
# 1) 初始化：契约字段机械提取 + 全字段占位骨架落盘
python3 scripts/render_contract.py init --case examples/synthetic-case.json \
    --work work/app/work --out work/app/output
# stdout: init ok: contract fields=[case_id, paper_id, material_version, status,
#   answers, coverage, sources, uncertainty, change_log]; skeleton -> work/app/output
# 骨架中 sources/uncertainty/change_log 均为占位值 "<待填>"。

# 2) 模型通读 5 段并填 sheets/Q1.md、Q2.md（略）

# 3) 部分渲染：extra_fields 未提供，非流水线字段降级为 WARN + 占位
python3 scripts/render_contract.py refresh --work work/app/work \
    --out work/app/output --legacy work/app/answers.json
# stdout: WARN: 契约字段 'sources' 流水线不产出… ×3；refresh ok: status=completed

# 4) 提供 extra_fields.json 后终检交付
python3 scripts/render_contract.py finalize --work work/app/work \
    --out work/app/output --legacy work/app/answers.json \
    --extra work/app/work/extra_fields.json
# stdout: finalize ok: status=completed
# cmp 验证：result.json 与 answers.json 逐字节相同。
```

## 故障注入验证（真实执行）

把 Q1 答题纸引文中 `and an elongation` 改为 `and elongation` 后：

```text
ERROR: Q1/Q1-C1: 引文不逐字（P2）: 'an ultimate tensile strength of 385 MPa and elonga'
finalize FAILED: 1 error(s)；产物未写。   （既有产物未被覆盖）
```

## 最终产物

`result.synthetic.json`：finalize 真实输出——契约 9 字段齐全，
`status=completed`，两题 answered，`sources/uncertainty/change_log`
由 extra_fields 并入。
