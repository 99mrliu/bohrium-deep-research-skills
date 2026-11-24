#!/usr/bin/env python3
"""plan_lint.py — narrative-first-deck 的叙事门禁（本方向 spike）。

在 build 之前校验 /app/work/storyline.json + /app/work/slide_plan.json：
  R1 coverage            页型覆盖 title/background/method/results/discussion/conclusion
  R2 one_claim_per_slide 一页一个主张；slide.claim_id 必须命中 storyline 中的 claim
  R3 evidence_anchor     每条 claim 至少 1 个证据锚点，且全部锚点能解析到抽取源（p.N/Figure N/Table N/章节）
  R4 figure_claim_binding 结果页展示 Figure N ⟺ 该页 claim 的 evidence_refs 引用 Figure N
  R5 order               页面 claim 顺序符合 storyline 依赖序（results 不得先于 method 等）
  R6 time_budget         从 task.md 解析 audience/duration（缺省 12 min）；按讲稿字数估算逐页秒数
                         （中文≈4 字/秒，英文≈2.2 词/秒），总和须落在 duration ±15% 内
  R7 numbers_verbatim    bullets 中的数字必须在源文本中逐字出现

输出 /app/output/plan_lint_report.json，并把被校验的 storyline 复制为 /app/output/storyline.json。
任何规则 fail → 退出码 1，且不进行构建；warn 不阻塞。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

REQUIRED_KINDS = ["title", "background", "method", "results", "discussion", "conclusion"]
DEFAULT_DURATION_MIN = 12
TOLERANCE = 0.15
CJK_RE = re.compile(r"[㐀-䶿一-鿿豈-﫿　-〿＀-￯]")
LATIN_WORD_RE = re.compile(r"[A-Za-z0-9]+(?:['’\-\.][A-Za-z0-9]+)*")


def estimate_seconds(text: str) -> float:
    """讲稿语速模型：中文（含中文标点）≈4 字/秒；英文/数字词 ≈2.2 词/秒。混合文本分段计。"""
    if not text:
        return 0.0
    cjk = len(CJK_RE.findall(text))
    latin = len(LATIN_WORD_RE.findall(CJK_RE.sub(" ", text)))
    return cjk / 4.0 + latin / 2.2


def norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def norm_fig_label(ref: str):
    m = re.search(r"figure\s*(\d+)", str(ref), re.I) or re.search(r"图\s*(\d+)", str(ref))
    return f"Figure {m.group(1)}" if m else None


def norm_tab_label(ref: str):
    m = re.search(r"table\s*(\d+)", str(ref), re.I) or re.search(r"表\s*(\d+)", str(ref))
    return f"Table {m.group(1)}" if m else None


class Linter:
    def __init__(self, work, output, task_text):
        self.work = Path(work)
        self.output = Path(output)
        self.task_text = task_text
        self.storyline = common.read_json(self.work / "storyline.json", {}) or {}
        self.plan = common.read_json(self.work / "slide_plan.json", {}) or {}
        self.slides = self.plan.get("slides", []) or []
        self.claims = self.storyline.get("claims", []) or []
        self.claim_by_id = {c.get("id"): c for c in self.claims}
        src = common.read_json(self.work / "paper" / "source_index.json", {}) or {}
        self.source = src
        self.full_text = common.read_text(src.get("full_text_path", "")) if src else ""
        self.fig_labels = {f.get("label") for f in src.get("figures", [])}
        self.tab_labels = {t.get("label") for t in src.get("tables", [])}
        self.n_pages = int(src.get("n_pages", 0) or 0)
        self.rules = []

    # ---- 各规则，返回 (verdict, details) ------------------------------------
    def r_coverage(self):
        kinds = [s.get("kind") for s in self.slides]
        missing = [k for k in REQUIRED_KINDS if k not in kinds]
        details = {"slide_kinds": kinds, "missing": missing}
        if missing:
            return "fail", {**details,
                            "message": f"缺页型: {missing}；六类页型(title→conclusion)必须齐备"}
        return "pass", details

    def r_one_claim(self):
        problems, used = [], {}
        for i, s in enumerate(self.slides, 1):
            cid = s.get("claim_id")
            if not cid:
                problems.append(f"slide {i} ({s.get('kind')}/{s.get('title','?')}): 缺少 claim_id")
                continue
            if cid not in self.claim_by_id:
                problems.append(f"slide {i}: claim_id '{cid}' 不在 storyline claims 中")
                continue
            used.setdefault(cid, []).append(i)
            sc = norm_ws(s.get("claim", ""))
            cc = norm_ws(self.claim_by_id[cid].get("text", ""))
            if sc and cc and sc != cc:
                problems.append(f"slide {i}: 页面 claim 文本与 storyline[{cid}] 不一致（warn 级）"
                                f" — 页:'{sc[:60]}' / 主线:'{cc[:60]}'")
        dup = {c: v for c, v in used.items() if len(v) > 1}
        for c, v in dup.items():
            problems.append(f"claim '{c}' 被多页复用 (slides {v})，违反一页一个主张")
        orphan = [c.get("id") for c in self.claims if c.get("id") not in used]
        hard = [p for p in problems if "warn 级" not in p]
        warns = [p for p in problems if "warn 级" in p]
        if orphan:
            warns.append(f"以下 storyline claims 未上任何页: {orphan}")
        verdict = "fail" if hard else ("warn" if warns else "pass")
        return verdict, {"problems": problems, "claim_to_slides": used}

    def _resolve_evidence(self, ev):
        """返回 (ok, resolved描述, quote_warn)。"""
        t = str(ev.get("type", "")).lower()
        ref = str(ev.get("ref", ""))
        quote_warn = None
        if t == "page":
            m = re.search(r"(\d+)", ref)
            ok = bool(m) and 1 <= int(m.group(1)) <= max(self.n_pages, 1)
            resolved = f"p.{m.group(1)}" if m else ref
        elif t == "figure":
            lab = norm_fig_label(ref)
            ok = lab in self.fig_labels if lab else False
            resolved = lab or ref
        elif t == "table":
            lab = norm_tab_label(ref)
            ok = lab in self.tab_labels if lab else False
            resolved = lab or ref
        elif t == "section":
            ok = bool(ref) and norm_ws(ref).lower() in norm_ws(self.full_text).lower()
            resolved = f"section:{ref}"
        else:
            ok, resolved = False, ref
        q = ev.get("quote")
        if ok and q and norm_ws(q) not in norm_ws(self.full_text):
            quote_warn = f"quote 未在源文本逐字命中: '{norm_ws(q)[:60]}...'"
        return ok, resolved, quote_warn

    def r_evidence_anchor(self):
        problems, warns, resolved_map = [], [], {}
        for c in self.claims:
            cid = c.get("id")
            refs = c.get("evidence_refs", []) or []
            if not refs:
                problems.append(f"claim '{cid}': 没有任何 evidence_refs")
                continue
            ok_list = []
            for ev in refs:
                ok, resolved, qw = self._resolve_evidence(ev)
                if not ok:
                    problems.append(f"claim '{cid}': 证据锚点 {ev.get('type')}:{ev.get('ref')} "
                                    f"无法解析到抽取源（n_pages={self.n_pages}, "
                                    f"figures={sorted(self.fig_labels)}, tables={sorted(self.tab_labels)}）")
                else:
                    ok_list.append(resolved)
                if qw:
                    warns.append(f"claim '{cid}': {qw}")
            if refs and not ok_list:
                problems.append(f"claim '{cid}': 所有证据锚点均不可解析")
            resolved_map[cid] = ok_list
        verdict = "fail" if problems else ("warn" if warns else "pass")
        return verdict, {"problems": problems, "warnings": warns, "resolved": resolved_map}

    def r_figure_binding(self):
        problems, warns = [], []
        for i, s in enumerate(self.slides, 1):
            cid = s.get("claim_id")
            claim = self.claim_by_id.get(cid)
            if not claim:
                continue
            claim_figs = {norm_fig_label(ev.get("ref"))
                          for ev in claim.get("evidence_refs", [])
                          if str(ev.get("type", "")).lower() == "figure"}
            claim_figs.discard(None)
            slide_figs = {norm_fig_label(f.get("ref")) for f in s.get("figures", [])}
            slide_figs.discard(None)
            for fr in sorted(slide_figs):
                if fr not in claim_figs:
                    problems.append(f"slide {i} ({s.get('kind')}): 展示 {fr}，但 claim '{cid}' 的 "
                                    f"evidence_refs 未引用该图 — 图上页必须绑定主张证据")
            if s.get("kind") == "results":
                for cf in sorted(claim_figs):
                    if cf not in slide_figs:
                        warns.append(f"slide {i}: claim '{cid}' 引用 {cf} 但页面未展示该图")
        verdict = "fail" if problems else ("warn" if warns else "pass")
        return verdict, {"problems": problems, "warnings": warns}

    def r_order(self):
        order_idx = {c.get("id"): k for k, c in enumerate(self.claims)}
        claim_slide = {}
        for i, s in enumerate(self.slides, 1):
            cid = s.get("claim_id")
            if cid in order_idx and cid not in claim_slide:
                claim_slide[cid] = i
        problems, warns = [], []
        prev, prev_slide = -1, None
        for i, s in enumerate(self.slides, 1):
            cid = s.get("claim_id")
            if cid not in order_idx:
                continue
            k = order_idx[cid]
            if k < prev:
                problems.append(f"slide {i} ({s.get('kind')}, claim '{cid}'): storyline 第 {k+1} 条主张，"
                                f"排在使用第 {prev+1} 条主张的 slide {prev_slide} 之后 — 叙事顺序倒退")
            prev, prev_slide = max(prev, k), i
            for dep in self.claim_by_id[cid].get("depends_on", []) or []:
                ds = claim_slide.get(dep)
                if ds is None:
                    warns.append(f"slide {i} claim '{cid}' 依赖 '{dep}'，但 '{dep}' 未上任何页")
                elif ds >= i:
                    problems.append(f"slide {i} (claim '{cid}') 依赖 claim '{dep}'，"
                                    f"但 '{dep}' 在 slide {ds} — 依赖必须先讲")
        verdict = "fail" if problems else ("warn" if warns else "pass")
        return verdict, {"problems": problems, "warnings": warns,
                         "slide_claim_sequence": [(i, s.get("claim_id"))
                                                  for i, s in enumerate(self.slides, 1)]}

    def r_time_budget(self):
        cons = common.parse_task_constraints(self.task_text)
        dur, dur_src = None, None
        if self.storyline.get("duration_min"):
            dur, dur_src = int(self.storyline["duration_min"]), "storyline.json"
        elif cons.get("duration_min"):
            dur, dur_src = cons["duration_min"], "task.md"
        else:
            dur, dur_src = DEFAULT_DURATION_MIN, f"fallback {DEFAULT_DURATION_MIN} min"
        audience = self.storyline.get("audience") or cons.get("audience") or "未指定"

        timeline, total, zero_notes = [], 0.0, []
        for i, s in enumerate(self.slides, 1):
            sec = estimate_seconds(s.get("notes", ""))
            if not (s.get("notes") or "").strip():
                zero_notes.append(i)
            total += sec
            timeline.append({"slide": i, "kind": s.get("kind"), "title": s.get("title", ""),
                             "seconds": round(sec), "cumulative_s": round(total)})
        lo, hi = dur * 60 * (1 - TOLERANCE), dur * 60 * (1 + TOLERANCE)
        warns, problems = [], []
        if not timeline:
            problems.append("无任何页面，无法计时")
        elif total == 0:
            warns.append("所有页 notes 为空：无法估计讲稿时长，计时预算未校验")
        elif not (lo <= total <= hi):
            problems.append(f"讲稿估计总长 {round(total)}s（{round(total/60, 1)}min）超出预算 "
                            f"[{round(lo)}s, {round(hi)}s]（duration={dur}min ±{int(TOLERANCE*100)}%，"
                            f"来源 {dur_src}）。最长页: "
                            + ", ".join(f"slide {t['slide']}={t['seconds']}s"
                                        for t in sorted(timeline, key=lambda x: -x["seconds"])[:3]))
        if zero_notes:
            warns.append(f"以下页 notes 为空（计 0s，拉低总时长可信度）: {zero_notes}")
        verdict = "fail" if problems else ("warn" if warns else "pass")
        return verdict, {"problems": problems, "warnings": warns,
                         "duration_min": dur, "duration_source": dur_src, "audience": audience,
                         "tolerance": TOLERANCE, "budget_seconds": [round(lo), round(hi)],
                         "total_seconds": round(total),
                         "model": "中文≈4字/秒；英文≈2.2词/秒；混合分段计；不含翻页与提问",
                         "timeline": timeline}

    def r_numbers_verbatim(self):
        problems = []
        full_norm = norm_ws(self.full_text)
        for i, s in enumerate(self.slides, 1):
            quotes = " ".join(str(ev.get("quote", "")) for ev in s.get("evidence", []) or [])
            hay = full_norm + " " + norm_ws(quotes)
            for b in s.get("bullets", []) or []:
                for tok in re.findall(r"\d+(?:\.\d+)?%?", str(b)):
                    if tok not in self.full_text and tok not in hay:
                        problems.append(f"slide {i} ({s.get('kind')}): bullet 中数字 '{tok}' "
                                        f"未在源文本逐字出现 — bullet: '{str(b)[:80]}'")
        verdict = "fail" if problems else "pass"
        return verdict, {"problems": problems}

    # ---- 主流程 --------------------------------------------------------------
    def run(self):
        checks = [("R1_coverage", self.r_coverage),
                  ("R2_one_claim_per_slide", self.r_one_claim),
                  ("R3_evidence_anchor", self.r_evidence_anchor),
                  ("R4_figure_claim_binding", self.r_figure_binding),
                  ("R5_order", self.r_order),
                  ("R6_time_budget", self.r_time_budget),
                  ("R7_numbers_verbatim", self.r_numbers_verbatim)]
        for name, fn in checks:
            try:
                verdict, details = fn()
            except Exception as e:  # noqa: BLE001
                verdict, details = "fail", {"exception": repr(e)}
            self.rules.append({"rule": name, "verdict": verdict, "details": details})
        fails = [r["rule"] for r in self.rules if r["verdict"] == "fail"]
        warns = [r["rule"] for r in self.rules if r["verdict"] == "warn"]
        overall = "fail" if fails else ("warn" if warns else "pass")
        report = {"linter": "narrative-first-deck plan_lint",
                  "generated_at": common.now_iso(),
                  "work_dir": str(self.work),
                  "n_slides": len(self.slides), "n_claims": len(self.claims),
                  "rules": self.rules, "overall": overall,
                  "fails": fails, "warns": warns}
        self.output.mkdir(parents=True, exist_ok=True)
        common.write_json(self.output / "plan_lint_report.json", report)
        # 被校验的 storyline 原样复制进交付目录（无论过没过，都留下证据）
        common.write_json(self.output / "storyline.json", self.storyline)
        return overall, report


def main(argv=None):
    ap = argparse.ArgumentParser(description="narrative-first-deck 叙事计划门禁")
    ap.add_argument("--work", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--input", default=None, help="用于读取 task.md 解析 audience/duration")
    ap.add_argument("--task", default=None, help="直接指定 task.md 路径（优先于 --input）")
    args = ap.parse_args(argv)
    task_text = ""
    if args.task:
        task_text = common.read_text(args.task)
    elif args.input:
        task_text = common.read_text(Path(args.input) / "task.md")
    overall, report = Linter(args.work, args.output, task_text).run()
    print(f"[plan_lint] overall={overall} fails={report['fails']} warns={report['warns']}")
    for r in report["rules"]:
        mark = {"pass": "✓", "warn": "!", "fail": "✗"}[r["verdict"]]
        print(f"  {mark} {r['rule']}: {r['verdict']}")
        for p in (r["details"].get("problems") or [])[:8]:
            print(f"      - {p}")
    print(f"[plan_lint] 报告: {Path(args.output) / 'plan_lint_report.json'}")
    return 1 if overall == "fail" else 0


if __name__ == "__main__":
    sys.exit(main())
