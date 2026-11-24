#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""audience_route.py — 受众画像路由器。

输入受众标签，从 references/audience_profiles.json 路由出画像，
生成 adaptation_plan.json（画像全量 + 可执行清单）。

退出码：
  0  成功（含 --fallback 兜底，结果中显式声明）
  1  用法错误 / 画像文件缺失或损坏 / 输入输出 IO 错误
  2  未知受众标签（且未指定 --fallback），stderr 给出可用标签列表
"""
import argparse
import json
import os
import re
import sys


def load_profiles(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_glossary(path):
    """加载 glossary.tsv（列为 source_term/approved_rendering/expansion/forbidden_synonyms）。

    以 '#' 开头的行为注释；首列等于 'source_term' 的行视为表头跳过。
    """
    terms = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.strip() or line.startswith("#"):
                continue
            parts = line.split("\t")
            if parts[0].strip() == "source_term":
                continue
            while len(parts) < 4:
                parts.append("")
            terms.append({
                "source_term": parts[0].strip(),
                "approved_rendering": parts[1].strip(),
                "expansion": parts[2].strip(),
                "forbidden_synonyms": [s.strip() for s in parts[3].split(",") if s.strip()],
            })
    return terms


def expansion_abbrev(expansion):
    """从 expansion 末位括号中提取全大写缩写（如 CCUS），没有则返回 None。"""
    m = re.search(r"[（(]([^（）()]*)[)）]\s*$", expansion)
    if not m:
        return None
    for seg in re.split(r"[；;]", m.group(1)):
        seg = seg.strip()
        if re.fullmatch(r"[A-Z][A-Z0-9]{1,}", seg):
            return seg
    return None


def main():
    default_profiles = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "references", "audience_profiles.json"
    )
    ap = argparse.ArgumentParser(description="受众画像路由：受众标签 → adaptation_plan.json")
    ap.add_argument("--audience", required=True, help="受众标签，如 public / grant_review / cross_discipline / bilingual_editor")
    ap.add_argument("--out", default=None, help="输出 adaptation_plan.json 路径（缺省打印到 stdout）")
    ap.add_argument("--glossary", default=None, help="可选 glossary.tsv，注入禁用表达与必展开缩写清单")
    ap.add_argument("--profiles", default=default_profiles, help="受众画像 JSON 路径")
    ap.add_argument("--fallback", action="store_true", help="未知标签时采用保守画像并在结果中声明")
    args = ap.parse_args()

    try:
        data = load_profiles(args.profiles)
    except (OSError, json.JSONDecodeError) as e:
        print(f"[ERROR] 无法加载受众画像文件 {args.profiles}: {e}", file=sys.stderr)
        return 1

    audiences = data.get("audiences", {})
    matched = args.audience in audiences
    if not matched and not args.fallback:
        print(f"[ERROR] 未知受众标签: {args.audience}", file=sys.stderr)
        print("可用标签: " + ", ".join(sorted(audiences)), file=sys.stderr)
        print("或追加 --fallback 采用保守画像（结果中将显式声明）", file=sys.stderr)
        return 2

    if matched:
        profile = dict(audiences[args.audience])
        fallback_used = False
        declaration = "命中内置受众画像。"
    else:
        profile = dict(data.get("fallback_profile", {}))
        fallback_used = True
        declaration = (
            f"未知受众标签 '{args.audience}'，已按 --fallback 采用保守画像："
            "全部缩写首次展开、术语密度从严、默认面向非专业读者。"
        )

    whitelist = profile.get("abbreviation_policy", {}).get("whitelist", [])
    checklist = {
        "abbreviation_handling": (
            profile.get("abbreviation_policy", {}).get("rule", "所有缩写首次出现必须展开")
            + "；白名单：" + "、".join(whitelist)
        ),
        "must_expand_abbreviations": [],
        "term_density_ceiling_per_100_chars": profile.get("term_density_ceiling"),
        "analogy_policy": profile.get("analogy_policy", {}),
        "structure_skeleton": profile.get("structure_template", []),
        "banned_expressions": list(profile.get("banned_expressions", [])),
        "length_guidance": profile.get("length_guidance", ""),
    }

    glossary_terms = []
    if args.glossary:
        try:
            glossary_terms = load_glossary(args.glossary)
        except OSError as e:
            print(f"[ERROR] 无法加载术语表 {args.glossary}: {e}", file=sys.stderr)
            return 1
        for t in glossary_terms:
            checklist["banned_expressions"].extend(t["forbidden_synonyms"])
            ab = expansion_abbrev(t["expansion"])
            if ab and ab not in whitelist and ab not in checklist["must_expand_abbreviations"]:
                checklist["must_expand_abbreviations"].append(ab)
        checklist["banned_expressions"] = sorted(set(checklist["banned_expressions"]))

    plan = {
        "tool": "audience_route.py",
        "audience": args.audience,
        "matched": matched,
        "fallback": fallback_used,
        "declaration": declaration,
        "profile": profile,
        "execution_checklist": checklist,
        "glossary_terms": glossary_terms,
        "notes": [
            "本计划只规定解释深度、术语密度、缩写展开与结构骨架，不预生成任何正文内容。",
            "配合 jargon_scan.py（行话密度与缩写展开）与 glossary_check.py（术语一致性）执行检查。",
        ],
    }

    text = json.dumps(plan, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        try:
            os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
            with open(args.out, "w", encoding="utf-8") as f:
                f.write(text)
        except OSError as e:
            print(f"[ERROR] 无法写出 {args.out}: {e}", file=sys.stderr)
            return 1
        print(f"[OK] adaptation_plan 已写出: {args.out} (audience={args.audience}, fallback={fallback_used})")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
