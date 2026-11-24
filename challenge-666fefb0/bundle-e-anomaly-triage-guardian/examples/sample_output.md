# 合成示例实际运行输出摘录

**本页为合成示例的真实运行记录（2026-11-24，macOS，Python 3 + pdftotext）。**
输入为 `make_fixture.py` 生成的演示数据，非正式案例结果。`fixture/` 由脚本生成，
不随 bundle 分发。

## 控制台输出

```
--- init (inventory + triage) ---
{"case_id": "case-synthetic-demo-e", "files": 16,
 "triage_classes": {"ok": 5, "corrupt_pdf": 1, "sidecar": 3, "empty_file": 1,
   "encrypted_pdf": 1, "garbled_encoding": 1, "permission_denied": 1,
   "no_text_layer": 1, "duplicate_bytes": 2}}
--- finalize (archive healthy + quarantine anomalies) ---
{"status": "partial", "ops": 16, "quarantined": 5, "skipped": 6, "verify_ok": true}
--- rerun idempotency check ---
{"status": "partial", "ops": 16, "quarantined": 5, "skipped": 6, "verify_ok": true}
```

## 隔离区树（异常原样保留，零丢失）

```
library/_quarantine/corrupt_pdf/corrupt-scan.pdf
library/_quarantine/empty_file/empty-download.pdf
library/_quarantine/encrypted_pdf/encrypted-report.pdf
library/_quarantine/garbled_encoding/legacy-gbk-notes.txt
library/_quarantine/no_text_layer/old-scanned-article.pdf
```

## result.json 的 skipped（诚实性要点）

```
F005 corrupt_pdf       -> library/_quarantine/corrupt_pdf/corrupt-scan.pdf
F007 empty_file        -> library/_quarantine/empty_file/empty-download.pdf
F008 encrypted_pdf     -> library/_quarantine/encrypted_pdf/encrypted-report.pdf
F009 garbled_encoding  -> library/_quarantine/garbled_encoding/legacy-gbk-notes.txt
F011 permission_denied -> None（源不可读，诚实注明"无法复制入隔离区；未丢失，仍在原路径"）
F013 no_text_layer     -> library/_quarantine/no_text_layer/old-scanned-article.pdf
```

加密 PDF 为真 `/Encrypt` 字典构造，pdftotext 报 "Incorrect password" →
分诊 `encrypted_pdf`，恢复建议 `pdftotext -upw 密码`。
`status=partial`；triage_summary 覆盖 9 个类别；verify 16/16 全覆盖。
