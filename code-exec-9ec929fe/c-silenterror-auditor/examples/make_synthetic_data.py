#!/usr/bin/env python3
"""生成合成示例的 SQLite 库 lab.db（无主键、含 NULL 与重复 id，人工合成）。"""
import os
import sqlite3
import sys

out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "synthetic_case", "lab.db")
if os.path.exists(out):
    os.remove(out)
con = sqlite3.connect(out)
con.execute("CREATE TABLE measurements (id TEXT, batch TEXT, reading REAL)")
con.executemany("INSERT INTO measurements VALUES (?,?,?)",
                [("R01", "A", 10.0), ("R02", "A", 11.0), ("R03", "A", None),
                 ("R04", "B", -999.0), ("R05", "B", 12.0), ("R05", "B", 12.0),
                 ("R06", "B", 13.0), ("R07", "C", 10.5), ("R08", "C", 11.5)])
con.commit()
con.execute("VACUUM")
con.close()
print("lab.db written:", out)
