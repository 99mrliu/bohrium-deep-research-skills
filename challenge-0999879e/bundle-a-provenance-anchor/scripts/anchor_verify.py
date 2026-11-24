#!/usr/bin/env python3
"""anchor_verify.py — finding 原文锚定的确定性复验。

子命令：
  scaffold   在 work 目录生成 findings_draft.json 空模板（供调用 Agent 填写）
  verify     对 findings_draft.json 每条的 original_text 做空白归一化后，
             在抽取文本全集（work/extracted/*.txt）中做子串复验，
             输出 work/anchor_report.json：
               - verified: 命中的条目（含命中文件与字符偏移）
               - not_found: 未命中的条目，标记 downgrade_to=pending_review 并写明理由
选项：
  --selftest 在独立临时目录构造小型语料，演示一条故意引错原文的 finding
             被判为 not_found（用于验收，不依赖真实输入）。

确定性保证：同一 inventory + 同一 findings_draft 必得同一 anchor_report
（文件排序、查找顺序、条目编号全部固定）。退出码：0 成功；非 0 失败。
"""
import argparse
import json
import os
import re
import sys
import tempfile

REPORT_VERSION = 1


def fail(msg, code=2):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def norm(s):
    """空白归一化：所有连续空白（含换行/制表）折叠为单个空格并去首尾。"""
    return re.sub(r"\s+", " ", s).strip()


def load_json(path, what):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return json.load(f)
    except FileNotFoundError:
        fail(f"缺少 {what}: {path}", code=3)
    except json.JSONDecodeError as e:
        fail(f"{what} 不是合法 JSON: {path}（{e}）", code=3)


def load_corpus(work_dir):
    """从 inventory.json 读取全部抽取文本，返回 [(file, text), ...]（按文件名排序）。"""
    inv = load_json(os.path.join(work_dir, "inventory.json"), "inventory.json（先运行 source_inventory.py）")
    corpus = []
    for entry in sorted(inv.get("files", []), key=lambda e: e["file"]):
        rel = entry.get("extracted_file")
        if not rel:
            continue
        p = os.path.join(work_dir, rel)
        if not os.path.isfile(p):
            continue
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            corpus.append((entry["file"], f.read()))
    return corpus


def load_findings(work_dir):
    data = load_json(os.path.join(work_dir, "findings_draft.json"),
                     "findings_draft.json（用 scaffold 生成模板后由 Agent 填写）")
    if isinstance(data, dict):
        data = data.get("findings", [])
    if not isinstance(data, list):
        fail("findings_draft.json 须为 finding 列表或含 findings 列表的对象", code=3)
    findings = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            fail(f"findings_draft[{i}] 不是对象", code=3)
        f = dict(item)
        fid = f.get("id")
        if not isinstance(fid, str) or not fid:
            fid = f"f-{i + 1:03d}"
        f["id"] = fid
        findings.append(f)
    return findings


def verify_corpus(findings, corpus):
    """核心复验逻辑（selftest 与 verify 共用）。返回 anchor_report dict。"""
    norm_corpus = [(name, norm(text)) for name, text in corpus]
    verified, not_found = [], []
    for f in findings:
        fid = f["id"]
        quote = f.get("original_text")
        if not isinstance(quote, str) or not quote.strip():
            not_found.append({
                "id": fid,
                "reason": "original_text 为空或缺失，无法锚定",
                "downgrade_to": "pending_review",
            })
            continue
        if len(quote) > 300:
            not_found.append({
                "id": fid,
                "reason": f"original_text 超长（{len(quote)} 字符 > 300），违反引用纪律，须缩短后重新锚定",
                "downgrade_to": "pending_review",
            })
            continue
        needle = norm(quote)
        hit = None
        for name, ntext in norm_corpus:
            off = ntext.find(needle)
            if off >= 0:
                hit = {"id": fid, "matched_file": name,
                       "char_offset_normalized": off,
                       "quote_chars": len(quote)}
                break
        if hit:
            verified.append(hit)
        else:
            not_found.append({
                "id": fid,
                "reason": "original_text 经空白归一化后未在任何抽取文本中出现（疑似凭记忆改写/引错原文）",
                "downgrade_to": "pending_review",
                "original_text_preview": quote[:80],
            })
    return {
        "report_version": REPORT_VERSION,
        "corpus_files": [name for name, _ in norm_corpus],
        "total_findings": len(findings),
        "verified_count": len(verified),
        "not_found_count": len(not_found),
        "verified": verified,
        "not_found": not_found,
    }


def cmd_scaffold(args):
    os.makedirs(args.work_dir, exist_ok=True)
    path = os.path.join(args.work_dir, "findings_draft.json")
    if os.path.isfile(path) and not args.force:
        fail(f"模板已存在: {path}（用 --force 覆盖）", code=4)
    template = {
        "_instructions": (
            "每条 finding 必填：id（f-001 起）、facet（六分面之一）、severity"
            "（critical/major/minor）、location（章节定位）、original_text（≤300字、"
            "逐字摘自稿件原文，锚定复验依据）、claim（问题陈述）、basis（判定依据）。"
            "original_text 找不到原文的条目会被自动降级为 pending_review。"
        ),
        "findings": [
            {
                "id": "f-001",
                "facet": "事实核验",
                "severity": "major",
                "location": "摘要",
                "original_text": "<在此粘贴稿件原文句子，逐字、≤300字>",
                "claim": "<问题陈述>",
                "basis": "<判定依据>"
            },
            {
                "id": "f-002",
                "facet": "引用支持",
                "severity": "minor",
                "location": "参考文献",
                "original_text": "<在此粘贴稿件原文句子，逐字、≤300字>",
                "claim": "<问题陈述>",
                "basis": "<判定依据>"
            }
        ],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(template, f, ensure_ascii=False, indent=2)
    print(json.dumps({"scaffold": path}, ensure_ascii=False))


def cmd_verify(args):
    findings = load_findings(args.work_dir)
    corpus = load_corpus(args.work_dir)
    if not corpus:
        fail("抽取文本全集为空：inventory 中没有任何 ok 的抽取结果，无法锚定", code=5)
    report = verify_corpus(findings, corpus)
    out = os.path.join(args.work_dir, "anchor_report.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps({
        "anchor_report": out,
        "total": report["total_findings"],
        "verified": report["verified_count"],
        "not_found": report["not_found_count"],
        "downgraded_ids": [e["id"] for e in report["not_found"]],
    }, ensure_ascii=False))


def cmd_selftest(args):
    with tempfile.TemporaryDirectory(prefix="anchor-selftest-") as td:
        ext_dir = os.path.join(td, "extracted")
        os.makedirs(ext_dir)
        genuine = "在优化条件下，甲醇产率达 92%，选择性为 95%。"
        with open(os.path.join(ext_dir, "00-manuscript.md.txt"), "w", encoding="utf-8") as f:
            f.write("# 合成稿件\n\n摘要：" + genuine + "\n")
        inv = {"files": [{"file": "manuscript.md",
                          "extracted_file": "extracted/00-manuscript.md.txt"}]}
        with open(os.path.join(td, "inventory.json"), "w", encoding="utf-8") as f:
            json.dump(inv, f, ensure_ascii=False)
        findings = [
            {"id": "f-ok", "original_text": genuine, "claim": "真实引用，应 verified"},
            {"id": "f-bad", "original_text": "本实验采用固定床反应器在 573 K 下进行评价",
             "claim": "故意引错：稿件中不存在此句，应 not_found 并降级"},
        ]
        corpus = load_corpus(td)
        report = verify_corpus(findings, corpus)
    ok_ids = [e["id"] for e in report["verified"]]
    bad = [e for e in report["not_found"] if e["id"] == "f-bad"]
    if ok_ids == ["f-ok"] and len(bad) == 1 and bad[0]["downgrade_to"] == "pending_review":
        print(json.dumps({
            "selftest": "PASS",
            "verified": ok_ids,
            "not_found": [{"id": b["id"], "downgrade_to": b["downgrade_to"],
                           "reason": b["reason"]} for b in bad],
        }, ensure_ascii=False))
        return
    print(json.dumps({"selftest": "FAIL", "report": report}, ensure_ascii=False),
          file=sys.stderr)
    sys.exit(1)


def main():
    ap = argparse.ArgumentParser(
        description="finding 原文锚定复验：verified / not_found（自动降级 pending_review）")
    ap.add_argument("--work-dir", default="/app/work", help="工作目录（默认 /app/work）")
    ap.add_argument("--force", action="store_true", help="scaffold 时覆盖已存在的模板")
    ap.add_argument("--selftest", action="store_true",
                    help="演示模式：故意引错原文的 finding 被判 not_found 后退出")
    ap.add_argument("command", nargs="?", choices=["scaffold", "verify"],
                    help="子命令（--selftest 时无需给出）")
    args = ap.parse_args()

    if args.selftest:
        cmd_selftest(args)
        return
    if args.command == "scaffold":
        cmd_scaffold(args)
    elif args.command == "verify":
        cmd_verify(args)
    else:
        ap.print_help(sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
