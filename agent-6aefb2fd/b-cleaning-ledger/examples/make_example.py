#!/usr/bin/env python3
"""合成示例（SYNTHETIC EXAMPLE，非正式案例结果）：
构造含完全重复、缺失、异常值的玩具表，端到端验证：
  - clean_ledger.py 正确删除/填补/标记且台账配平；
  - ledger_check.py 独立复核通过；
  - 篡改台账后 ledger_check.py 拒绝（退出码 5）。

用法：python3 make_example.py [输出根目录，默认 /tmp/cl-example]
"""
import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "/tmp/cl-example")
HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "scripts")
WORK = os.path.join(ROOT, "work")
os.makedirs(WORK, exist_ok=True)

# --- 合成玩具数据（与任何真实案例无关）：30 行，x 含 2 个缺失+1 个极端值，
#     y 为类别列含 1 个缺失，另有 3 条完全重复行 ---
base = []
for i in range(30):
    x = 10.0 + (i % 10)
    y = ["a", "b", "c"][i % 3]
    base.append((x, y))
base[5] = (None, "b")      # x 缺失（1/30=3.3% ≤5% → 中位数填补）
base[29] = (999.0, "c")    # x 极端值
base[11] = (base[11][0], None)  # y 缺失（众数填补）
rows = base + [base[0], base[1], base[2]]  # 3 条完全重复
raw_path = os.path.join(WORK, "raw_toy.csv")
with open(raw_path, "w", encoding="utf-8") as f:
    f.write("x,y\n")
    for x, y in rows:
        f.write(f"{'' if x is None else x},{'' if y is None else y}\n")


def run(cmd, expect=0):
    print("+", " ".join(cmd))
    r = subprocess.run(cmd, capture_output=True, text=True)
    sys.stdout.write(r.stdout)
    sys.stderr.write(r.stderr)
    assert r.returncode == expect, f"退出码 {r.returncode} != 预期 {expect}"
    return r


run([sys.executable, os.path.join(SCRIPTS, "clean_ledger.py"),
     "--table", raw_path, "--name", "toy", "--out", WORK])
led = json.load(open(os.path.join(WORK, "cleaning_ledger.json"), encoding="utf-8"))
assert led["balanced"] and led["initial_rows"] == 33 and led["final_rows"] == 30
assert led["entries"][1]["rows_removed"] == 3            # R2 重复
assert led["entries"][2 + (0 if len(led["entries"]) == 4 else 0)]  # 分录存在
r4 = next(e for e in led["entries"] if e["seq"] == "R4")
assert r4["cells_modified"] == 2, r4                     # x 1 格 + y 1 格填补
flags = open(os.path.join(WORK, "toy_outlier_flags.csv"), encoding="utf-8").read()
assert "999.0" in flags
print("CHECK OK: 33->30 行，删除 3 重复，填补 2 格，999.0 被标记且未删除，台账配平")

run([sys.executable, os.path.join(SCRIPTS, "ledger_check.py"),
     "--table", raw_path, "--name", "toy", "--work", WORK])
print("CHECK OK: 独立复核通过")

# 篡改台账（把 R2 删除数改小 1）→ 复核必须拒绝
bak = os.path.join(WORK, "cleaning_ledger.json.bak")
shutil.copy(os.path.join(WORK, "cleaning_ledger.json"), bak)
led["entries"][1]["rows_removed"] = 2
led["total_rows_removed"] = 2
json.dump(led, open(os.path.join(WORK, "cleaning_ledger.json"), "w",
                    encoding="utf-8"), ensure_ascii=False, indent=2)
r = run([sys.executable, os.path.join(SCRIPTS, "ledger_check.py"),
         "--table", raw_path, "--name", "toy", "--work", WORK], expect=5)
assert "LEDGER_CHECK_FAIL" in r.stderr
print("CHECK OK: 篡改台账被独立复核抓获（退出码 5）")
shutil.move(bak, os.path.join(WORK, "cleaning_ledger.json"))
run([sys.executable, os.path.join(SCRIPTS, "ledger_check.py"),
     "--table", raw_path, "--name", "toy", "--work", WORK])
print("SYNTHETIC EXAMPLE PASSED ->", ROOT)
