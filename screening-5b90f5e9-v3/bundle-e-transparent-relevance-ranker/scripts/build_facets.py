#!/usr/bin/env python3
"""build_facets.py — facet 骨架生成与模型填写结果校验。

两种模式：
  --init               从 config 的 facet_weights 与研究问题生成骨架
                       <work>/facets_skeleton.json（terms 留空，由模型填写）。
                       骨架只建结构：词表内容一律由模型在运行时根据研究问题填写。
  --validate <file>    校验模型填好的 facets 文件：
                         1) facet 键集合必须与 config.facet_weights 完全一致；
                         2) 每个 facet 的 terms 为非空、去重、长度>=2 的字符串列表；
                         3) 若文件里回显了 weight，必须与 config 一致（权重只能改 config）。
                       校验失败 exit 3（门禁），模型必须重修后再提交。

退出码：0 正常；3 校验/结构失败。
"""
import argparse
import sys
from pathlib import Path

from common_lib import (default_config_path, dump_json, eprint, load_config,
                        load_json, norm_text)


def cmd_init(work, cfg, facets_path=None):
    summary_path = work / "case_summary.json"
    question = None
    if summary_path.exists():
        question = load_json(summary_path).get("research_question")
    skeleton = {
        "research_question": question,
        "fill_instructions": [
            "由模型为每个 facet 填写 terms：2-6 个会在题录题名/摘要中真实出现的词或短语",
            "term 必须与题录文本可锚定（anchor_hits.py 将做规范化子串校验，零命中词会触发 exit 3）",
            "中英文同义词可并列；不要填权重，权重以 config/scoring_config.json 为准",
            "不要新增或删除 facet；facet 集合由 config.facet_weights 决定",
        ],
        "facets": {name: {"terms": []} for name in cfg["facet_weights"]},
    }
    out = facets_path or (work / "facets_skeleton.json")
    if Path(out).exists():
        # 幂等且防误覆盖：骨架已存在（可能已被模型编辑）时不覆盖
        print(f"[build_facets] 骨架已存在，跳过生成: {out}")
        return 0
    dump_json(out, skeleton)
    print(f"[build_facets] 骨架已生成: {out}（{len(skeleton['facets'])} 个 facet，terms 待模型填写）")
    return 0


def cmd_validate(filled_path, cfg):
    errors = []
    filled = load_json(filled_path)
    facets = filled.get("facets")
    if not isinstance(facets, dict):
        errors.append("缺少 facets 对象")
        facets = {}

    expected = set(cfg["facet_weights"])
    got = set(facets)
    if got != expected:
        errors.append(f"facet 集合与 config 不一致: 多 {sorted(got - expected)}，缺 {sorted(expected - got)}")

    for name in sorted(expected & got):
        node = facets[name]
        terms = node.get("terms") if isinstance(node, dict) else None
        if not isinstance(terms, list) or not terms:
            errors.append(f"facet {name}: terms 缺失或为空")
            continue
        seen = set()
        for t in terms:
            if not isinstance(t, str) or len(norm_text(t)) < 2:
                errors.append(f"facet {name}: 非法 term（非字符串或规范化后长度<2）: {t!r}")
                continue
            key = norm_text(t)
            if key in seen:
                errors.append(f"facet {name}: term 规范化后重复: {t!r}")
            seen.add(key)
        if "weight" in node and abs(float(node["weight"]) - float(cfg["facet_weights"][name])) > 1e-9:
            errors.append(f"facet {name}: 回显 weight 与 config 不一致；权重只能在 config 中修改")

    if errors:
        for e in errors:
            eprint(f"[build_facets] 校验失败: {e}")
        return 3
    print(f"[build_facets] 校验通过: {filled_path}（{len(facets)} 个 facet）")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="facet 骨架生成与校验")
    ap.add_argument("--init", action="store_true", help="生成骨架")
    ap.add_argument("--validate", metavar="FILE", help="校验模型填好的 facets 文件")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--config", default=default_config_path())
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    work = Path(args.work)
    if args.init:
        return cmd_init(work, cfg)
    if args.validate:
        return cmd_validate(args.validate, cfg)
    eprint("[build_facets] 必须指定 --init 或 --validate FILE")
    return 3


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:
        eprint(f"[build_facets] 未预期异常: {exc!r}")
        sys.exit(3)
