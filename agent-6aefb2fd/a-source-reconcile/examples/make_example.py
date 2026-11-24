#!/usr/bin/env python3
"""合成示例（SYNTHETIC EXAMPLE，非正式案例结果）：
构造一个玩具双源案例（CSV 快照 + SQLite，植入 1 处单元格差异与 1 个完全重复行），
端到端运行 source_audit.py 与 result_ledger.py，验证：
  - 对账能定位到具体列与行；
  - 主源裁决按规则给出；
  - result.json 契约镜像与 seal 校验真实执行。

用法：python3 make_example.py [输出根目录，默认 /tmp/sr-example]
"""
import json
import os
import sqlite3
import subprocess
import sys

ROOT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "/tmp/sr-example")
HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "scripts")
INP = os.path.join(ROOT, "input")
WORK = os.path.join(ROOT, "work")
OUT = os.path.join(ROOT, "output")
for d in (INP, WORK, OUT):
    os.makedirs(d, exist_ok=True)

# --- 合成输入（玩具数据，三列 12 行；与任何真实案例无关）---
rows = [(1.0 + i, 2.5 * i, "g" + str(i % 3)) for i in range(12)]
rows[7] = (8.0, 17.5, "g1")  # 将在 SQLite 中被改动为 18.5
csv_path = os.path.join(INP, "toy_snapshot.csv")
with open(csv_path, "w", encoding="utf-8") as f:
    f.write("alpha,beta,label\n")
    for a, b, l in rows:
        f.write(f"{a},{b},{l}\n")
    f.write("1.0,0.0,g0\n")  # 完全重复第一行 → 供裁决扣分演示
db_path = os.path.join(INP, "toy.sqlite")
if os.path.exists(db_path):
    os.remove(db_path)
con = sqlite3.connect(db_path)
con.execute("create table toy (alpha real, beta real, label text)")
rows_db = list(rows)
rows_db[7] = (8.0, 18.5, "g1")  # 植入差异：beta 17.5 -> 18.5
rows_db.append((1.0, 0.0, "g0"))  # 双源均含完全重复行（行数保持一致）
con.executemany("insert into toy values (?,?,?)", rows_db)
con.commit()
con.close()
case = {"case_id": "synthetic-toy-001",
        "materials": [{"path": "toy_snapshot.csv"}, {"path": "toy.sqlite"}],
        "output_contract": {"fields": [{"name": n} for n in
            ["cleaned_data", "statistics", "figures", "report", "quality_evidence", "exceptions"]]}}
json.dump(case, open(os.path.join(INP, "case.json"), "w", encoding="utf-8"), ensure_ascii=False)


def run(cmd):
    print("+", " ".join(cmd))
    r = subprocess.run(cmd, capture_output=True, text=True)
    sys.stdout.write(r.stdout)
    sys.stderr.write(r.stderr)
    assert r.returncode == 0, f"失败退出 {r.returncode}"
    return r


audit = run([sys.executable, os.path.join(SCRIPTS, "source_audit.py"),
             "--input", INP, "--case", os.path.join(INP, "case.json"), "--out", WORK])
a = json.load(open(os.path.join(WORK, "source_audit.json"), encoding="utf-8"))
rec = a["reconciliations"][0]
assert rec["verdict"] == "content_divergent", rec["verdict"]
assert rec["diff_by_column"]["beta"]["examples"][0]["row"] == 7
# 双源均含重复行（各 −1），快照文件 +2 vs 数据库 +1 → CSV 裁决为主源
assert a["adjudication"]["primary"] == "toy_snapshot.csv", a["adjudication"]
print("CHECK OK: 差异定位 beta 列第 7 行；主源裁决 toy_snapshot.csv（快照 +2 对数据库 +1，重复行各 −1）")

res = os.path.join(OUT, "result.json")
run([sys.executable, os.path.join(SCRIPTS, "result_ledger.py"), "init",
     "--case", os.path.join(INP, "case.json"), "--out", res])
# 故意只填部分字段 → seal success 必须拒绝
run([sys.executable, os.path.join(SCRIPTS, "result_ledger.py"), "fill", "--out", res,
     "--set", "cleaned_data=/tmp/sr-example/output/cleaned.csv"])
open(os.path.join(OUT, "cleaned.csv"), "w", encoding="utf-8").write("alpha,beta,label\n")
r = subprocess.run([sys.executable, os.path.join(SCRIPTS, "result_ledger.py"), "seal",
                    "--case", os.path.join(INP, "case.json"), "--out", res,
                    "--status", "success"], capture_output=True, text=True)
assert r.returncode == 3 and "SEAL_REFUSE" in r.stderr, (r.returncode, r.stderr)
print("CHECK OK: 契约字段不全时 seal 拒绝 success（退出码 3）")
run([sys.executable, os.path.join(SCRIPTS, "result_ledger.py"), "note", "--out", res,
     "--uncertainty", "示例：beta 列第 7 行双源不一致，其余字段未在示例中生产"])
r = subprocess.run([sys.executable, os.path.join(SCRIPTS, "result_ledger.py"), "seal",
                    "--case", os.path.join(INP, "case.json"), "--out", res,
                    "--status", "partial"], capture_output=True, text=True)
assert r.returncode == 0
final = json.load(open(res, encoding="utf-8"))
assert final["case_id"] == "synthetic-toy-001" and final["status"] == "partial"
assert len(final["sources"]) == 2 and final["uncertainty"]
print("CHECK OK: partial 诚实封口，sources 来自审计哈希")
print("SYNTHETIC EXAMPLE PASSED ->", ROOT)
