# 最小调用示例（Walkthrough）

以下命令在技能包根目录执行，使用 `examples/fixtures/` 中的**合成虚构数据**完整走一遍
"登记 → 骨架 → 审计（正例/反例/容差）"流程。所有输出块均为真实运行的输出，标注为
示意输出（合成示例）。

设 `S` 指向脚本目录（运行时优先 `/skills/weekly-skill/scripts`，本地回退为 `./scripts`）：

```bash
S=/skills/weekly-skill/scripts
[ -d "$S" ] || S=scripts
```

## 0. 端到端自测

```bash
python3 scripts/selfcheck.py; echo "exit=$?"
```

示意输出（合成示例）：

```
[PASS] source_register 登记夹具源文件 — 登记完成：6 个文件 → /private/var/folders/7r/mnfbx0px1j14kpqsr2bp7nyc0000gn/T/brain/vaeg_selfcheck_8xa_31ax/registry.json（其中 OCR 容差预声明 1 个，pdftotext=可用）
[PASS] quote_audit(result_ok) 通过 (exit 0) — 汇总：6 个锚点全部通过（精确 6，声明式容差 0）。审计通过。
[PASS] quote_audit(result_bad_forged) 失败 (exit 1) — FAIL $.evidence_records[0]: quote 不是源文件 src_patent_EX1001.txt 的逐字子串（quote not found）
[PASS] quote_audit(result_bad_tolerant_undeclared) 失败 (exit 1) — FAIL $.candidates[0].anchors[0]: quote 非逐字子串，存在疑似 OCR 噪声的近似匹配，但容差未声明（锚点未声明 tolerance_used:true）—— 未声明的容差匹配一律判失败（undeclared tolerance）
[PASS] scaffold_result(case_fixture) case_id 与契约镜像正确 — case_id=SYNTH-EXAMPLE-001, 契约字段镜像=['candidates', 'evidence_records', 'related_literature', 'sources', 'status', 'uncertainty']
------------------------------------------------------------
自查通过：5/5 断言全部 PASS。
exit=0
```

## 1. 登记输入源（含 OCR 容差预声明）

```bash
python3 $S/source_register.py \
  --roots examples/fixtures/src_patent_EX1001.txt \
  --roots examples/fixtures/src_paper_EX2001.txt \
  --out /tmp/vaeg_demo/registry.json \
  --tolerance-ocr examples/fixtures/src_patent_EX1001.txt
echo "exit=$?"
```

示意输出（合成示例）：

```
登记完成：2 个文件 → /tmp/vaeg_demo/registry.json（其中 OCR 容差预声明 1 个，pdftotext=可用）
exit=0
```

## 2. 生成诚实 partial 骨架（最先落盘，再迭代）

```bash
python3 $S/scaffold_result.py --case examples/fixtures/case_fixture.json \
  --out /tmp/vaeg_demo/output --status partial
echo "exit=$?"
cat /tmp/vaeg_demo/output/result.json
```

示意输出（合成示例）：

```
骨架已写入 /tmp/vaeg_demo/output/result.json（case_id=SYNTH-EXAMPLE-001, status=partial, 契约镜像字段 6 个）
exit=0
{
  "candidates": null,
  "evidence_records": null,
  "related_literature": null,
  "status": "partial",
  "sources": [],
  "uncertainty": [],
  "case_id": "SYNTH-EXAMPLE-001",
  "change_records": [
    {
      "ts": "2026-11-24T08:41:31Z",
      "action": "scaffold",
      "status": "partial",
      "note": "由 scaffold_result.py 生成的诚实骨架：先落盘 partial，再迭代改进。"
    }
  ]
}
```

## 3. 审计正例：result_ok.json（全部 quote 逐字命中）

```bash
python3 $S/quote_audit.py --result examples/fixtures/result_ok.json \
  --registry /tmp/vaeg_demo/registry.json
echo "exit=$?"
```

示意输出（合成示例）：

```
汇总：6 个锚点全部通过（精确 6，声明式容差 0）。审计通过。
exit=0
```

## 4. 审计反例一：编造的 quote（result_bad_forged.json）

`evidence_records[0]` 的 quote 为 `同族成员：US9999999ZZ9；JP9999999ZZ9（编造同族）`，
不存在于任何登记源文件：

```bash
python3 $S/quote_audit.py --result examples/fixtures/result_bad_forged.json \
  --registry /tmp/vaeg_demo/registry.json
echo "exit=$?"
```

示意输出（合成示例）：

```
FAIL $.evidence_records[0]: quote 不是源文件 src_patent_EX1001.txt 的逐字子串（quote not found）
汇总：6 个锚点，1 失败（精确通过 5，容差通过 0）。审计不通过。
exit=1
```

## 5. 审计反例二：OCR 噪声近似匹配但未声明容差（result_bad_tolerant_undeclared.json）

`candidates[0].anchors[0]` 的 quote 把源文中的 `公开号：US0000000EX1` 误写为
`公开号：USO000000EX1`（`0`→`O`），且锚点未携带 `tolerance_used: true`：

```bash
python3 $S/quote_audit.py --result examples/fixtures/result_bad_tolerant_undeclared.json \
  --registry /tmp/vaeg_demo/registry.json
echo "exit=$?"
```

示意输出（合成示例）：

```
FAIL $.candidates[0].anchors[0]: quote 非逐字子串，存在疑似 OCR 噪声的近似匹配，但容差未声明（锚点未声明 tolerance_used:true）—— 未声明的容差匹配一律判失败（undeclared tolerance）
汇总：6 个锚点，1 失败（精确通过 5，容差通过 0）。审计不通过。
exit=1
```

## 6. 对照：双重声明后的容差匹配可通过

若登记时已 `--tolerance-ocr`（见第 1 步）且锚点显式声明 `tolerance_used: true`，
同样的 OCR 噪声 quote 才允许以编辑距离容差通过：

```bash
cat > /tmp/vaeg_demo/result_declared_tolerance.json <<'EOF'
{
  "case_id": "SYNTH-EXAMPLE-001",
  "status": "partial",
  "evidence_records": [
    {
      "field": "demo.ocr",
      "quote": "公开号：USO000000EX1",
      "source_path": "examples/fixtures/src_patent_EX1001.txt",
      "source_sha256": "f00306a0da902858ece0a6f7504de9023629f1833f49d88edc1bb2303f6c3bd9",
      "tolerance_used": true
    }
  ]
}
EOF
python3 $S/quote_audit.py --result /tmp/vaeg_demo/result_declared_tolerance.json \
  --registry /tmp/vaeg_demo/registry.json
echo "exit=$?"
```

示意输出（合成示例）：

```
汇总：1 个锚点全部通过（精确 0，声明式容差 1）。审计通过。
exit=0
```

> 注意：本步演示文件写在 /tmp，仅为对照说明；正式交付中每个容差锚点都必须在
> `uncertainty` 里追加说明（见 references/tolerance_declaration.md 第 5 节）。
