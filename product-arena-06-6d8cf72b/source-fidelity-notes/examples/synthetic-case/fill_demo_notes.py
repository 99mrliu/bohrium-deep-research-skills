#!/usr/bin/env python3
"""fill_demo_notes.py -- 合成示例的 notes.json 生成器。

仅用于本地演示接口：从扫描产物中提取锚点并把固定的合成论断写成
notes.json。标注：SYNTHETIC EXAMPLE，非真实论文、非正式案例结果。
"""
import argparse
import json


def find_line(source, needle):
    for page in source["pages"]:
        for ln in page["lines"]:
            if needle in ln["text"]:
                return ln["anchor"], ln["text"]
    return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    with open(args.scan + "/source.json", encoding="utf-8") as fh:
        source = json.load(fh)

    def claim(needle, quote):
        anchor, line = find_line(source, needle)
        assert anchor, "fixture line missing: " + needle
        assert quote in line, "fixture quote mismatch"
        return {"anchor": anchor, "quote": quote}

    cycles = claim("survived a mean of 420 cycles", "420 cycles (n = 6, sd = 31)")
    ysz = claim("the YSZ baseline survived 265 cycles", "265 cycles (n = 6, sd = 24)")
    por = claim("Porosity was 14 percent", "14 percent for Aerolite-7")
    cave = claim("the difference was not significant", "the difference was not significant")
    ero = claim("We did not test erosion resistance", "We did not test erosion resistance")

    notes = {
        "result_fields": {
            "answer": {
                "main_finding": "在 1100 C 炉循环实验中，Aerolite-7 涂层平均存活 420 次循环，"
                                "高于 YSZ 基线的 265 次（合成示例论断）。",
                "key_numbers": [
                    {"value": 420, "meaning": "Aerolite-7 平均循环寿命", **cycles},
                    {"value": 265, "meaning": "YSZ 基线平均循环寿命", **ysz},
                    {"value": "14 percent", "meaning": "Aerolite-7 孔隙率", **por},
                ],
            },
            "evidence": {
                "main_finding": {"anchor": cycles["anchor"], "quote": cycles["quote"]},
            },
            "limitations_kept": [
                {"claim": "900 C 下差异不显著，结论仅限 1100 C 条件。",
                 "anchor": cave["anchor"], "quote": cave["quote"]},
                {"claim": "未测试抗冲蚀性能；莫来石原料为实验室级。",
                 "anchor": ero["anchor"], "quote": ero["quote"]},
            ],
        },
        "sources": [{"doc_id": source["doc_id"], "sha256": source["sha256"],
                     "backend": source["backend"], "path": "paper.txt (synthetic fixture)"}],
        "null_reasons": {},
        "limits": ["SYNTHETIC EXAMPLE：虚构论文，仅演示接口，非正式案例结果。"],
        "uncertainty": [],
        "change_records": [],
    }
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(notes, fh, ensure_ascii=False, indent=2)
    print("wrote", args.out)


if __name__ == "__main__":
    main()
