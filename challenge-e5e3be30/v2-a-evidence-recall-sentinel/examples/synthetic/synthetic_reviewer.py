#!/usr/bin/env python3
"""Fixed simulated Agent review for the SYNTHETIC demo; not production adjudication.

This harness reads real generated candidate IDs and contexts. It does not generate
or copy a final result. The production skill requires the Agent to write review.json.
"""
import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--work", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    work = Path(args.work)
    candidates = [json.loads(line) for line in (work / "candidates.jsonl").read_text(encoding="utf-8").splitlines() if line]
    plan = json.loads((work / "retrieval-plan.json").read_text(encoding="utf-8"))
    candidate_reviews = {}
    s1_evidence = []
    for candidate in candidates:
        cid = candidate["candidate_id"]
        if candidate["claim_id"] == "S1" and "neutrophil count decreased" in candidate["context"].casefold() and "18.0%" in candidate["context"]:
            candidate_reviews[cid] = {
                "status": "reviewed",
                "relevant": True,
                "exclusion_reason": None,
                "note": "SYNTHETIC Agent: the table reports the queried arm, event grade, and rate using synonymous event wording."
            }
            s1_evidence.append(cid)
        else:
            candidate_reviews[cid] = {
                "status": "reviewed",
                "relevant": False,
                "exclusion_reason": "SYNTHETIC Agent: this candidate does not report both the pediatric subgroup and the 36-month overall-survival end point." if candidate["claim_id"] == "S2" else "SYNTHETIC Agent: candidate lacks the requested adverse-event arm, grade, or numeric rate.",
                "note": "Topical similarity alone is not support."
            }
    claim_reviews = {
        "S1": {
            "verdict": "supported" if s1_evidence else "insufficient_evidence",
            "rationale": "SYNTHETIC Agent semantic review: page 2 Table 2 explicitly reports grade 3 neutrophil count decreased in 4/20 (18.0%) of AST 7. The initial family made no hit; the synonym/table family recovered this candidate.",
            "evidence_candidate_ids": s1_evidence,
            "conflicts": [],
            "uncertainty": "Demonstration only; no real-world clinical claim is made."
        },
        "S2": {
            "verdict": "insufficient_evidence",
            "rationale": "SYNTHETIC Agent semantic review: all candidates concern adults, other end points, or 24-month follow-up. None reports the requested pediatric 36-month rate. Non-reporting is not contradiction.",
            "evidence_candidate_ids": [],
            "conflicts": [],
            "uncertainty": "Only the supplied three-page synthetic document was searched."
        }
    }
    present = {c["claim_id"] for c in plan["claims"]}
    claim_reviews = {cid: value for cid, value in claim_reviews.items() if cid in present}
    review = {
        "label": "SYNTHETIC fixed simulated Agent review / 合成示例模拟裁决",
        "claim_reviews": claim_reviews,
        "candidate_reviews": candidate_reviews,
        "result_overrides": {"run_note": "SYNTHETIC / 合成示例，不是官方答案；所有结果由实际运行生成。"}
    }
    Path(args.output).write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"SYNTHETIC reviewer wrote {len(claim_reviews)} claim reviews and {len(candidate_reviews)} candidate reviews")


if __name__ == "__main__":
    main()
