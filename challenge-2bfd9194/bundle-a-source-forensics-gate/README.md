# source-forensics-gate

科研资料**入库前逐文件真实性取证** Skill：未经验证真实性的文件不得作为可信资料入库。

## 用途

对混杂的科研文件先做取证关卡——魔数签名比对（抓改名伪装）、文本编码探测、
损坏/截断启发检查（PDF 缺 `%%EOF`、ZIP 缺 EOCD、PNG 缺 IEND、JPEG 缺 `FF D9`）、
零字节/不可读识别、流式 SHA-256——给出
`authentic / type_mismatch / corrupt_suspect / empty / unreadable` 五档判定；
通过者按桶入库（papers/ data/ scans/ supplementary/ drafts/ admin/ _unassigned/），
未通过者隔离进 `library/_quarantine/`（保留原相对路径），并同时完成内容去重
（canonical=mtime 最早）、版本链（supersedes 边）与冲突 `__vN` 消解。

## 运行

```
python3 scripts/run_case.py all --input /input --work /app/work --out /app/output
```

分阶段：`init / scan / forensics / plan / apply / verify / finalize`（同参数）。
独立校验：`python3 scripts/verify_forensics.py --input /input --out /app/output`。

## 输出（/app/output/）

`result.json`、`library/`、`LIBRARY_MANIFEST.jsonl`、`FORENSICS_REPORT.json`、
`duplicates.json`、`version_chains.json`、`operations_journal.jsonl`、
`skipped_and_conflicts.json`、`QA_LOG.json`、`audit_report.json`。

## 限制

- 仅 Python 3 标准库；不联网；只读 /input；复制不移动，绝不覆盖已有不同内容。
- 只做字节级真实性取证，不解析文件内容语义（不抽取作者/年份/DOI，不 OCR）。
- 存在隔离项时 result.json 状态至多 `partial`（诚实状态，非缺陷）。
- 合成示例见 `examples/`（非正式案例结果）。
