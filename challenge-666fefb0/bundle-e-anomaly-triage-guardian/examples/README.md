# 最小调用示例（合成示例）

**声明：本示例为合成示例。** 夹具文件、回答与输出均为演示数据，不对应真实文献，
也不是平台正式案例结果。

## 运行

```bash
cd examples
python3 make_fixture.py     # 生成合成夹具 fixture/input（16 个文件，覆盖 8 类异常）
bash run_example.sh         # init(分诊) -> 预写回答 -> finalize(归档+隔离)
```

## 夹具异常覆盖

| 文件 | 分诊类别 |
|---|---|
| corrupt-scan.pdf | corrupt_pdf |
| encrypted-report.pdf（真 /Encrypt 字典） | encrypted_pdf |
| old-scanned-article.pdf | no_text_layer |
| no-permission.pdf（chmod 0） | permission_denied |
| empty-download.pdf | empty_file |
| legacy-gbk-notes.txt（GBK 字节） | garbled_encoding |
| quantum dots review final.pdf、thesis-copy-again.pdf | duplicate_bytes |

## 观察点

- `triage_report.md`：16 文件逐一分类，检测证据与恢复建议逐条可复核；
- `_quarantine/<类别>/`：异常文件原样保留（permission_denied 源不可读，
  诚实记 `preserved_at: null` 而非谎称已隔离）；
- result.json：`status=partial`，skipped 含 triage_class 与 recovery；
- 重跑 finalize 幂等。

实际运行输出摘录见 `sample_output.md`。
