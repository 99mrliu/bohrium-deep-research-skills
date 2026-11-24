#!/usr/bin/env python3
"""生成合成示例的 SQLite 库 lab.db（人工合成数据，非正式案例材料）。
每次运行生成逐字节一致的库：先删旧文件、固定行序。"""
import os
import sqlite3
import sys

out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "synthetic_case", "lab.db")
if os.path.exists(out):
    os.remove(out)
con = sqlite3.connect(out)
con.execute("CREATE TABLE batches (batch TEXT PRIMARY KEY, operator TEXT, n_registered INTEGER)")
con.execute("CREATE TABLE specimens (sample_id TEXT PRIMARY KEY, batch TEXT, strength REAL)")
con.executemany("INSERT INTO batches VALUES (?,?,?)",
                [("A", "op1", 4), ("B", "op2", 4), ("C", "op1", 4)])
con.executemany("INSERT INTO specimens VALUES (?,?,?)",
                [("M01", "A", 61.9), ("M02", "A", 60.8), ("M04", "A", 45.3),
                 ("M05", "B", 22.1), ("M06", "B", 55.4), ("M08", "B", 62.3),
                 ("M09", "C", 19.8), ("M10", "C", 51.2), ("M11", "C", 51.7),
                 ("M12", "C", 25.6)])
con.commit()
con.execute("VACUUM")
con.close()
print("lab.db written:", out)
