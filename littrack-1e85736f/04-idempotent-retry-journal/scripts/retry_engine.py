#!/usr/bin/env python3
"""retry_engine.py — 失败重试与断点续跑引擎（离线，仅标准库）。

主循环：对 case.json 中每个「源 × 窗口」：
  1. checkpoint 已完成 -> 直接跳过（不写新日志，不产生新事件）；
  2. 否则读取本地固化材料，交给 failure_classify 分类；
  3. 成功 -> 归一化题录、经 delivery_dedup 幂等投递、立即写 checkpoint；
  4. 失败 -> 按确定性退避表计划重试（离线不 sleep，只记录计划与决策），
     重试耗尽/阻断 -> 记入 checkpoint.degraded，诚实降级。

产出（全部在 --work 目录）：
  retry_journal.jsonl   每次尝试一条：attempt_no、故障类别、退避计划、决策
  checkpoint.json       源×窗口粒度的完成/降级状态
  delivery_log.jsonl    幂等投递账本
  runs.jsonl            每轮运行摘要（供 change_records 组装）

CLI:
  python3 retry_engine.py --case /path/case.json --work /app/work
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import checkpoint as ck
import delivery_dedup as dd
import failure_classify as fc

JOURNAL_NAME = "retry_journal.jsonl"
RUNS_NAME = "runs.jsonl"
CHECKPOINT_NAME = "checkpoint.json"
DELIVERY_LOG_NAME = "delivery_log.jsonl"


def utcnow():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def append_jsonl(path, obj):
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def count_lines(path):
    if not os.path.exists(path):
        return 0
    with open(path, "r", encoding="utf-8") as f:
        return sum(1 for line in f if line.strip())


def normalize_record(rec):
    """把三种已知结构的记录归一化成 {doi, title, extra}。"""
    doi = rec.get("DOI") or rec.get("doi") or rec.get("id") or ""
    title = rec.get("title") or rec.get("title_text") or ""
    if isinstance(title, list):
        title = " ".join(str(t) for t in title if t)
    extra = {}
    for k in ("container-title", "journalTitle", "publisher", "published",
              "pubYear", "URL", "url", "author"):
        if k in rec:
            extra[k] = rec[k]
    return {"doi": str(doi), "title": str(title), "extra": extra}


def run_case(case_path, work_dir, log=print):
    """执行一轮增量导入。返回本轮统计 dict。"""
    with open(case_path, "r", encoding="utf-8") as f:
        case = json.load(f)
    case_dir = os.path.dirname(os.path.abspath(case_path))
    case_id = case["case_id"]
    default_window = case.get("window", {}).get("id", "default")

    os.makedirs(work_dir, exist_ok=True)
    journal_path = os.path.join(work_dir, JOURNAL_NAME)
    runs_path = os.path.join(work_dir, RUNS_NAME)
    cp_path = os.path.join(work_dir, CHECKPOINT_NAME)
    dlog_path = os.path.join(work_dir, DELIVERY_LOG_NAME)

    run_no = count_lines(runs_path) + 1
    started = utcnow()
    cp = ck.load(cp_path, case_id=case_id)

    stats = {"run_no": run_no, "skipped_completed": 0, "processed": 0,
             "degraded": 0, "blocked": 0, "delivered": 0,
             "dedup_skipped": 0, "records_skipped": 0, "empty_windows": 0}

    for src in case.get("sources", []):
        sid = src["source_id"]
        material = src["material"]
        if not os.path.isabs(material):
            material = os.path.normpath(os.path.join(case_dir, material))
        material_rel = os.path.relpath(material, case_dir)
        for window in src.get("windows", [default_window]):
            key = ck.make_key(sid, window)

            # —— 幂等跳过：已完成的源×窗口不再处理、不产生新事件 ——
            if ck.is_completed(cp, sid, window):
                stats["skipped_completed"] += 1
                log("  [skip] %s 已完成，跳过（checkpoint 命中）" % key)
                continue

            # —— 尝试循环：失败按确定性退避表计划重试 ——
            attempt = 1
            terminal = None  # (decision, verdict) 终止态
            while True:
                verdict = fc.load_and_classify(material)
                if verdict["ok"]:
                    entry = {"ts": utcnow(), "run_no": run_no,
                             "case_id": case_id, "event": "attempt",
                             "source": sid, "window": window,
                             "attempt_no": attempt,
                             "failure_class": verdict["failure_class"],
                             "backoff_plan_seconds": None,
                             "decision": "success",
                             "material": material_rel}
                    append_jsonl(journal_path, entry)
                    terminal = ("success", verdict)
                    break
                fclass = verdict["failure_class"]
                strategy = fc.STRATEGY[fclass]
                sched = fc.BACKOFF_SCHEDULE[fclass]
                # 最多 MAX_ATTEMPTS 次尝试：前 MAX-1 次失败计划退避重试，
                # 第 MAX_ATTEMPTS 次仍失败则终止（降级/阻断）
                if strategy == "retry" and attempt < fc.MAX_ATTEMPTS:
                    decision = ("retry_scheduled(+%ds, planned-only)"
                                % sched[attempt - 1])
                    append_jsonl(journal_path, {
                        "ts": utcnow(), "run_no": run_no, "case_id": case_id,
                        "event": "attempt", "source": sid, "window": window,
                        "attempt_no": attempt, "failure_class": fclass,
                        "backoff_plan_seconds": sched[attempt - 1],
                        "decision": decision, "detail": verdict["detail"],
                        "material": material_rel})
                    log("  [retry] %s attempt %d: %s -> %s"
                        % (key, attempt, fclass, decision))
                    attempt += 1
                    continue
                if strategy == "retry":
                    decision = "degrade_source(retries_exhausted)"
                elif strategy == "block":
                    decision = "block_source(manual_review_required)"
                else:
                    decision = "degrade_source(%s)" % fclass
                append_jsonl(journal_path, {
                    "ts": utcnow(), "run_no": run_no, "case_id": case_id,
                    "event": "attempt", "source": sid, "window": window,
                    "attempt_no": attempt, "failure_class": fclass,
                    "backoff_plan_seconds": None,
                    "decision": decision, "detail": verdict["detail"],
                    "material": material_rel})
                log("  [%s] %s: %s -> %s"
                    % ("block" if strategy == "block" else "degrade",
                       key, fclass, decision))
                terminal = (decision, verdict)
                break

            decision, verdict = terminal
            if decision == "success":
                stats["processed"] += 1
                delivered = dups = rec_skipped = 0
                skipped_recs = []
                pointer = verdict["items_pointer"] or ""
                issue_idx = {i["index"] for i in verdict["record_issues"]}
                for i, rec in enumerate(verdict["items"]):
                    locator = "%s#%s/%d" % (material_rel, pointer, i)
                    if i in issue_idx:
                        issue = next(x for x in verdict["record_issues"]
                                     if x["index"] == i)
                        rec_skipped += 1
                        skipped_recs.append({
                            "locator": locator,
                            "failure_class": "missing_field",
                            "missing": issue["missing"]})
                        log("  [skip-record] %s 缺字段 %s"
                            % (locator, ",".join(issue["missing"])))
                        continue
                    norm = normalize_record(rec)
                    item_key = norm["doi"] or ("%s#%d" % (sid, i))
                    record = {
                        "delivery_key": dd.delivery_key(case_id, window,
                                                        item_key),
                        "case_id": case_id, "window": window, "source": sid,
                        "doi": norm["doi"], "title": norm["title"],
                        "extra": norm["extra"],
                        "locator": locator, "run_no": run_no,
                    }
                    if dd.append_if_new(dlog_path, record):
                        delivered += 1
                    else:
                        dups += 1
                        log("  [dedup] 抑制重复投递 %s" % record["delivery_key"])
                note = ("empty_window" if verdict["failure_class"]
                        == "empty_window" else "ok")
                if verdict["failure_class"] == "empty_window":
                    stats["empty_windows"] += 1
                ck.mark_completed(cp, sid, window, run_no, delivered, dups,
                                  records_skipped=skipped_recs, note=note)
                ck.save(cp_path, cp)  # 每个源完成立即落盘
                stats["delivered"] += delivered
                stats["dedup_skipped"] += dups
                stats["records_skipped"] += rec_skipped
                log("  [done] %s delivered=%d dedup=%d rec_skipped=%d (%s)"
                    % (key, delivered, dups, rec_skipped, note))
            else:
                fclass = verdict["failure_class"]
                ck.mark_degraded(cp, sid, window, fclass,
                                 verdict["detail"], attempt, run_no)
                ck.save(cp_path, cp)
                stats["degraded"] += 1
                if fc.STRATEGY[fclass] == "block":
                    stats["blocked"] += 1

    append_jsonl(runs_path, dict({"ts_start": started, "ts_end": utcnow(),
                                  "case_id": case_id}, **stats))
    log("run #%d 完成: %s" % (run_no, json.dumps(stats, ensure_ascii=False)))
    return stats


def main(argv):
    ap = argparse.ArgumentParser(description="idempotent retry engine (offline)")
    ap.add_argument("--case", required=True, help="path to case.json")
    ap.add_argument("--work", required=True,
                    help="work dir for journal/checkpoint/delivery log")
    args = ap.parse_args(argv[1:])
    run_case(args.case, args.work)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
