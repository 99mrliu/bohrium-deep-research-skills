#!/usr/bin/env python3
"""生成合成示例的 SQLite 库 lab.db（人工合成数据，确定性重建）。"""
import os
import sqlite3
import sys

out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "synthetic_case", "lab.db")
if os.path.exists(out):
    os.remove(out)
con = sqlite3.connect(out)
con.execute("CREATE TABLE registry (sid TEXT, channel TEXT)")
con.executemany("INSERT INTO registry VALUES (?,?)",
                [("S1", "ch1"), ("S2", "ch1"), ("S3", "ch1"),
                 ("S4", "ch2"), ("S5", "ch2"), ("S6", "ch2")])
con.commit()
con.execute("VACUUM")
con.close()
print("lab.db written:", out)
