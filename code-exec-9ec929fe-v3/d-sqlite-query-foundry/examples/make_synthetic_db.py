#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成合成示例库 examples/output_demo/sensors_syn.db（纯虚构传感器网络，仅供演示）。

数据集设计（全部为编造数据，与任何真实数据无关）：
  sites(site_id, region)                8 个站点，site 8 故意没有任何读数。
  readings(reading_id, site_id, ts, value, status)
    约 200 行，刻意包含：
      - 部分 value 为 NULL 的行；
      - 部分 status='void' 的行（语义上必须被过滤）；
      - 一个故意埋设的陷阱：site 1 的 18 条 valid 记录（其中 1 条 value
        为 NULL）被以新的 reading_id 原样重复插入（同一批物理读数重复
        入库），使朴素 valid 计数（status='valid' AND value IS NOT NULL）
        偏多 17。本示例用它演示行数对账与 reconcile 独立复核如何
        把重复暴露出来（见 reconcile_claim.json 的第 3 项检查）。
"""
import random
import sqlite3
from pathlib import Path

OUT = Path(__file__).resolve().parent / "output_demo" / "sensors_syn.db"

SITES = [
    (1, "north"), (2, "north"), (3, "south"), (4, "south"),
    (5, "east"), (6, "west"), (7, "west"), (8, "east"),  # site 8 无读数
]


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if OUT.exists():
        OUT.unlink()
    conn = sqlite3.connect(OUT)
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE sites(
            site_id INTEGER PRIMARY KEY,
            region  TEXT NOT NULL
        );
        CREATE TABLE readings(
            reading_id INTEGER PRIMARY KEY,
            site_id    INTEGER NOT NULL REFERENCES sites(site_id),
            ts         TEXT NOT NULL,
            value      REAL,
            status     TEXT NOT NULL
        );
        """
    )
    cur.executemany("INSERT INTO sites VALUES (?, ?)", SITES)

    rng = random.Random(20261124)
    rows = []
    rid = 1
    for sid in range(1, 8):  # site 1..7，site 8 无读数
        for k in range(26):  # 7 * 26 = 182 条基础读数
            ts = "2026-11-%02dT%02d:00:00Z" % (k % 28 + 1, k % 24)
            value = round(rng.uniform(10.0, 90.0), 2)
            status = "valid"
            if k % 13 == 5:
                status = "void"   # 每站 2 条 void，必须被过滤
            if k % 17 == 9:
                value = None      # 每站 1~2 条 NULL value
            rows.append((rid, sid, ts, value, status))
            rid += 1

    # ---- 故意埋设的陷阱：重复批次 ----
    # 同一批 (site_id, ts, value, status) 以不同 reading_id 再插一次。
    # 语义上这是重复入库；朴素 COUNT 会把它们再计一次，导致行数偏多
    # （18 条中 1 条 value 为 NULL，故朴素 valid 计数偏多 17）。
    dup_source = [r for r in rows if r[1] == 1 and r[4] == "valid"][:18]
    for _rid, sid, ts, value, status in dup_source:
        rows.append((rid, sid, ts, value, status))
        rid += 1

    cur.executemany("INSERT INTO readings VALUES (?, ?, ?, ?, ?)", rows)
    conn.commit()

    total = cur.execute("SELECT COUNT(*) FROM readings").fetchone()[0]
    naive_valid = cur.execute(
        "SELECT COUNT(*) FROM readings WHERE status='valid' AND value IS NOT NULL"
    ).fetchone()[0]
    dedup_valid = cur.execute(
        "SELECT COUNT(*) FROM (SELECT DISTINCT site_id, ts, value FROM readings "
        "WHERE status='valid' AND value IS NOT NULL)"
    ).fetchone()[0]
    conn.close()
    print("已生成：%s" % OUT)
    print("readings 总行数：%d" % total)
    print("朴素 valid 计数（含重复批次）：%d" % naive_valid)
    print("去重后 valid 计数：%d（重复 %d 行）" % (dedup_valid, naive_valid - dedup_valid))


if __name__ == "__main__":
    main()
