#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
anchor_audit.py — 论断锚核验 + 输入完整性证明 + result.json 装配

流程：
  1. 读取 work 目录下的 manifest.json / anchor_index.json（由 forensic_intake.py 生成）；
  2. 对输入目录全部材料 re-hash，与 manifest 比对 → 输入完整性证明（pass/fail）；
  3. 扫描交付稿，抽取全部 [Mx:Ly] / [Mx:py] 锚（支持区间 [Mx:L10-L12]），逐个解析回
     材料原文，检查：(a) 锚是否存在（材料号、行/页范围有效、锚种类匹配）；
     (b) 锚位原文与论断句是否共享至少一个关键 token（数字、≥4 字符英文词、
     中文 4 字滑窗）——不满足标 ANCHOR-MISMATCH；
     (c) 含数字或"表明/显示/证明/达到"等事实线索却无锚的句子标 UNANCHORED-CLAIM；
     句内带【待确认】标记的记为 PENDING（豁免但公示）；
  4. 写 audit_report.md；按 case.json 的 output_contract 装配 result.json，
     字段无内容填 "PENDING"，不删字段；case_id 原样照抄。

退出码：0 流程成功（审计结论见报告）；1 硬失败（缺文件/坏 JSON）；
        3 审计未通过或完整性失败（仅 --strict 模式，供 CI 卡口使用）。
"""

import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path

# 锚语法：[M2:L18] / [M1:p3] / 区间 [M2:L4-L6]（也兼容 [M2:L4-6]）
ANCHOR_RE = re.compile(r"\[M(\d+):(L|p)(\d+)(?:-[Lp]?(\d+))?\]")
# 事实线索：含数字，或含下列中文动词/结构
FACT_CUES = ("表明", "显示", "证明", "证实", "指出", "提升", "提高",
             "下降", "降低", "达到", "占比", "约为", "超过")
PENDING_MARK = "【待确认】"


def sha256_of(path: Path) -> str:
    """流式 SHA-256，与 intake 保持一致。"""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------- 交付稿切句 ----------

def iter_checkable_sentences(text: str):
    """逐行扫描交付稿：跳过代码块、标题、引用、表格与 audit-skip 行，再按句末标点切句。"""
    in_code = False
    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if line.startswith("```"):
            in_code = not in_code
            continue
        if in_code or not line:
            continue
        if line.startswith("#") or line.startswith(">") or line.startswith("|"):
            continue
        if "audit-skip" in line:
            continue
        for sent in re.split(r"(?<=[。！？!?])|(?<=[.])\s+|(?<=;)\s+", line):
            sent = sent.strip()
            if sent:
                yield sent


def merge_anchor_fragments(sents):
    """锚若落在句末标点之后会成为"纯锚碎片"，合并回上一句。"""
    merged = []
    pure = re.compile(r"(\[M\d+:(?:L|p)\d+(?:-[Lp]?\d+)?\][\s，,。.;；]*)+$")
    for s in sents:
        if pure.fullmatch(s) and merged:
            merged[-1] += " " + s
        else:
            merged.append(s)
    return merged


def is_factual(sent: str) -> bool:
    """事实句判定：含数字，或含事实线索词。"""
    if re.search(r"\d", sent):
        return True
    return any(c in sent for c in FACT_CUES)


# ---------- 关键 token 与锚解析 ----------

def key_tokens(text: str):
    """关键 token：数字（可带小数/%）、≥4 字符英文词、中文 4 字滑窗。"""
    text = ANCHOR_RE.sub(" ", text)
    toks = set(re.findall(r"\d+(?:\.\d+)?%?", text))
    for w in re.findall(r"[A-Za-z][A-Za-z0-9_\-]*", text):
        if len(w) >= 4:
            toks.add(w.lower())
    for run in re.findall(r"[\u4e00-\u9fff]+", text):
        if len(run) >= 4:
            toks.add(run)
        for i in range(0, max(0, len(run) - 3)):
            toks.add(run[i:i + 4])
    return toks


def resolve_anchor(anchor_index, work_dir: Path, mid: str, kind: str, a: int, b):
    """把锚解析回材料原文片段。返回 (excerpt, 错误原因或 None)。"""
    entry = anchor_index.get(f"M{mid}")
    if entry is None:
        return None, "MATERIAL-NOT-FOUND"
    want = "line" if kind == "L" else "page"
    if entry["kind"] != want:
        return None, f"KIND-MISMATCH(该材料为{entry['kind']}锚)"
    hi = b if b else a
    if a < 1 or hi > entry["count"] or hi < a:
        return None, f"OUT-OF-RANGE(有效范围 1-{entry['count']})"
    src = work_dir / entry["extracted"]
    if want == "line":
        lines = src.read_text(encoding="utf-8").split("\n")
        ctx = lines[max(0, a - 3):hi + 2]  # 上下文 ±2 行
        excerpt = "\n".join(ctx).strip()[:400]
    else:
        pages = json.loads(src.read_text(encoding="utf-8"))
        excerpt = "\n".join(pages[a - 1:hi])[:200]  # 该页文本前 200 字符
    return excerpt, None


# ---------- 主流程 ----------

def main() -> int:
    ap = argparse.ArgumentParser(description="论断锚核验 + 完整性证明 + result.json 装配")
    ap.add_argument("--work", required=True, help="intake 工作目录（含 manifest.json 等）")
    ap.add_argument("--input", required=True, help="原始输入目录（用于 re-hash 完整性比对）")
    ap.add_argument("--case", required=True, help="case.json 路径（读取 output_contract 与 case_id）")
    ap.add_argument("--deliverable", required=True, help="待核验的交付稿（Markdown）")
    ap.add_argument("--output", required=True, help="输出目录（评测时为 /app/output）")
    ap.add_argument("--strict", action="store_true", help="审计未通过或完整性失败时以退出码 3 卡口")
    ap.add_argument("--note", default=None, help="附加说明，写入报告头部与 result.json 的 note 字段")
    args = ap.parse_args()

    work_dir = Path(args.work)
    in_dir = Path(args.input)
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    deliverable = Path(args.deliverable)

    # ---- 硬失败检查 ----
    for p, name in [(work_dir / "manifest.json", "manifest.json"),
                    (work_dir / "anchor_index.json", "anchor_index.json"),
                    (Path(args.case), "case.json"),
                    (deliverable, "deliverable")]:
        if not p.is_file():
            print(f"[audit] 硬失败：缺少 {name} -> {p}", file=sys.stderr)
            return 1
    try:
        manifest = json.loads((work_dir / "manifest.json").read_text(encoding="utf-8"))
        anchor_index = json.loads((work_dir / "anchor_index.json").read_text(encoding="utf-8"))
        case = json.loads(Path(args.case).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"[audit] 硬失败：JSON 解析错误 {exc}", file=sys.stderr)
        return 1

    now = time.strftime("%Y-%m-%dT%H:%M:%S%z")

    # ---- 1. 输入完整性证明：re-hash 全部输入并与 manifest 比对 ----
    integrity = "pass"
    integrity_detail = []
    for m in manifest["materials"]:
        p = in_dir / m["path"]
        if not p.is_file():
            integrity = "fail"
            integrity_detail.append(f"{m['id']} {m['path']} 缺失")
            continue
        digest = sha256_of(p)
        if digest != m["sha256"]:
            integrity = "fail"
            integrity_detail.append(f"{m['id']} {m['path']} 哈希已变化")

    # ---- 2. 论断锚核验 ----
    text = deliverable.read_text(encoding="utf-8")
    sentences = merge_anchor_fragments(list(iter_checkable_sentences(text)))

    anchor_records = []   # 每个锚的核验记录
    unanchored = []       # 无锚事实句
    pending_sents = []    # 带【待确认】的句子
    preserved = []        # 通过核验的带锚事实句
    for sent in sentences:
        anchors = list(ANCHOR_RE.finditer(sent))
        if PENDING_MARK in sent:
            pending_sents.append(sent)
            continue
        if not anchors:
            if is_factual(sent):
                unanchored.append(sent)
            continue
        claim = ANCHOR_RE.sub("", sent).strip()
        toks = key_tokens(sent)
        all_ok = True
        for m in anchors:
            mid, kind, a, b = m.group(1), m.group(2), int(m.group(3)), m.group(4)
            b = int(b) if b else None
            anchor_str = m.group(0).strip("[]")
            excerpt, err = resolve_anchor(anchor_index, work_dir, mid, kind, a, b)
            status = "OK"
            if err:
                status = f"ANCHOR-INVALID:{err}"
                all_ok = False
            elif toks:
                low = excerpt.lower()
                if not any(t in low for t in toks):
                    status = "ANCHOR-MISMATCH"
                    all_ok = False
            anchor_records.append({
                "anchor": anchor_str, "claim": claim, "status": status,
                "material": f"M{mid}", "excerpt": (excerpt or "")[:200],
            })
        if all_ok and is_factual(sent):
            preserved.append(sent)

    n_total = len(anchor_records)
    n_ok = sum(1 for r in anchor_records if r["status"] == "OK")
    n_bad = n_total - n_ok
    verdict_pass = (n_bad == 0 and len(unanchored) == 0)

    # ---- 3. audit_report.md ----
    lines = []
    lines.append("# 论断锚核验报告")
    if args.note:
        lines.append(f"\n> {args.note}")
    lines.append(f"\n- 时间：{now}")
    lines.append(f"- 交付稿：{deliverable.name}")
    lines.append(f"- 输入完整性：**{integrity}**" +
                 ("" if integrity == "pass" else "（" + "；".join(integrity_detail) + "）"))
    lines.append(f"- 锚总数：{n_total}；通过 {n_ok}；异常 {n_bad}；"
                 f"无锚事实句 {len(unanchored)}；待确认 {len(pending_sents)}")
    lines.append(f"- 结论：**{'PASS' if verdict_pass else 'FAIL'}**"
                 "（UNANCHORED-CLAIM 与 ANCHOR-MISMATCH 必须处理——补锚/删除/标【待确认】——方可通过）")
    if anchor_records:
        lines.append("\n## 锚逐条核验\n")
        lines.append("| 锚 | 状态 | 论断句（截断） | 锚位原文（截断） |")
        lines.append("|---|---|---|---|")
        for r in anchor_records:
            c = r["claim"].replace("|", "\\|")[:60]
            e = r["excerpt"].replace("|", "\\|").replace("\n", " / ")[:80]
            lines.append(f"| [{r['anchor']}] | {r['status']} | {c} | {e} |")
    if unanchored:
        lines.append("\n## UNANCHORED-CLAIM（需补锚/删除/标【待确认】）\n")
        for s in unanchored:
            lines.append(f"- {s}")
    if pending_sents:
        lines.append("\n## PENDING（已标【待确认】，豁免但公示）\n")
        for s in pending_sents:
            lines.append(f"- {s}")
    (out_dir / "audit_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # ---- 4. 装配 result.json ----
    contract = case.get("output_contract")
    if not isinstance(contract, dict):
        contract = {}
    result = {k: "PENDING" for k in contract}          # 契约字段先占位，不删字段
    result["case_id"] = case.get("case_id", "PENDING")  # case_id 原样照抄
    result["deliverable"] = deliverable.name
    result["preserved_facts"] = preserved if preserved else "PENDING"
    evidence_map = {}
    for r in anchor_records:
        evidence_map[r["anchor"]] = {
            "material": r["material"], "status": r["status"],
            "claim": r["claim"], "excerpt": r["excerpt"],
        }
    result["evidence_map"] = evidence_map if evidence_map else "PENDING"
    result["change_log"] = [
        {"time": manifest.get("generated_at"), "action": "forensic_intake",
         "detail": f"建库 {manifest.get('material_count')} 份材料，记录 SHA-256 基线"},
        {"time": now, "action": "anchor_audit",
         "detail": f"核验锚 {n_total} 个，通过 {n_ok}，异常 {n_bad}，无锚事实句 {len(unanchored)}"},
    ]
    gaps = [f"{m['id']}({m['path']}): {m['status']}"
            for m in manifest["materials"]
            if m["status"] in ("extractor_unavailable", "non_text_material", "no_text_layer")
            or str(m["status"]).startswith("extractor_error")]
    uncertainty = list(gaps)
    if n_bad:
        uncertainty.append(f"{n_bad} 个锚核验异常，详见 audit_report.md")
    if unanchored:
        uncertainty.append(f"{len(unanchored)} 句无锚事实句，详见 audit_report.md")
    if integrity == "fail":
        uncertainty.append("输入完整性校验失败：" + "；".join(integrity_detail))
    result["sources"] = manifest["materials"]
    result["uncertainty"] = uncertainty if uncertainty else "无已知不确定项"
    result["integrity_check"] = integrity
    result["forensics"] = {
        "materials": len(manifest["materials"]),
        "anchors_total": n_total,
        "anchors_ok": n_ok,
        "anchor_mismatch_or_invalid": n_bad,
        "unanchored_claims": len(unanchored),
        "pending_claims": len(pending_sents),
        "pass_rate": (n_ok / n_total) if n_total else None,
        "integrity_check": integrity,
        "extractor_gaps": gaps,
    }
    result["status"] = "complete" if (verdict_pass and integrity == "pass") else "partial"
    if args.note:
        result["note"] = args.note
    (out_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[audit] 锚 {n_total}：OK {n_ok} / 异常 {n_bad}；无锚事实句 {len(unanchored)}；"
          f"完整性 {integrity}；结论 {'PASS' if verdict_pass else 'FAIL'}；status={result['status']}")
    print(f"[audit] 产物：{out_dir}/audit_report.md, result.json")
    if args.strict and (not verdict_pass or integrity != "pass"):
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
