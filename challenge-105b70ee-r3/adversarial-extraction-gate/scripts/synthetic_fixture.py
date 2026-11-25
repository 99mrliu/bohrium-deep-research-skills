"""Entirely synthetic fixture; no official case, paper, answer, or score is used."""
from __future__ import annotations

import copy
from typing import Any, Dict, List, Tuple

CASE_ID = "SYNTHETIC-ADVERSARIAL-GATE-V1"


def targets() -> List[Dict[str, Any]]:
    return [
        {
            "field_id": "syn_response",
            "subject": "SynA",
            "experimental_condition": "condition C",
            "comparator": "comparator D",
            "statistic_required": True,
            "description": "SYNTHETIC numeric response request; not an official target.",
        },
        {
            "field_id": "syn_unmeasured",
            "subject": "SynA",
            "experimental_condition": "condition C",
            "comparator": "comparator D",
            "description": "SYNTHETIC absent measurement; not an official target.",
        },
    ]


def corpus() -> Dict[str, Any]:
    return {
        "schema": "evidence-corpus/v1",
        "synthetic": True,
        "sources": [{
            "source_id": "synthetic-source",
            "title": "SYNTHETIC source text for validator testing",
            "paragraphs": [
                {
                    "page": 1,
                    "paragraph_id": "p1",
                    "text": "For SynA under condition C, versus comparator D, mean ± SD response was 12.4 nM. This sentence and all values are synthetic.",
                },
                {
                    "page": 1,
                    "paragraph_id": "p2",
                    "text": "The investigators suggest SynA may alter downstream signaling under condition C. This is synthetic hedged text.",
                },
                {
                    "page": 2,
                    "paragraph_id": "p3",
                    "text": "The synthetic protocol lists SynA and condition C but contains no second response measurement.",
                },
            ],
        }],
    }


def _reported_field() -> Dict[str, Any]:
    quote = "For SynA under condition C, versus comparator D, mean ± SD response was 12.4 nM."
    return {
        "field_id": "syn_response",
        "status": "reported",
        "subject": "SynA",
        "scalar": "12.4",
        "units": "nM",
        "statistic": "mean ± SD",
        "experimental_condition": "condition C",
        "condition": "condition C",
        "comparator": "comparator D",
        "paragraph_id": "p1",
        "quote": quote,
        "evidence": {
            "source_id": "synthetic-source",
            "page": 1,
            "paragraph_id": "p1",
            "quote": quote,
        },
        "notes": "SYNTHETIC example value; literal numeric extraction only.",
    }


def valid_result() -> Dict[str, Any]:
    fields = [
        _reported_field(),
        {
            "field_id": "syn_unmeasured",
            "status": "not_reported",
            "subject": "SynA",
            "scalar": None,
            "units": None,
            "statistic": None,
            "experimental_condition": "condition C",
            "condition": "condition C",
            "comparator": "comparator D",
            "paragraph_id": None,
            "quote": None,
            "evidence": None,
            "notes": "SYNTHETIC full-corpus fixture has no requested second response; this is not zero.",
        },
    ]
    return {
        "case_id": CASE_ID,
        "status": "answered",
        "result": {
            "fields": copy.deepcopy(fields),
            "field_results": copy.deepcopy(fields),
        },
        "claims": [{
            "claim_id": "synthetic-claim-1",
            "kind": "speculation",
            "statement": "The investigators suggest SynA may alter downstream signaling under condition C.",
            "source_id": "synthetic-source",
            "location": {"page": 1, "paragraph_id": "p2"},
            "evidence": {
                "source_id": "synthetic-source",
                "page": 1,
                "paragraph_id": "p2",
                "quote": "The investigators suggest SynA may alter downstream signaling under condition C.",
            },
        }],
        "uncertainties": [{
            "field_id": "syn_unmeasured",
            "kind": "not_reported",
            "description": "SYNTHETIC absent measurement; absence is not evidence of a zero value.",
        }],
        "sources": [{"source_id": "synthetic-source", "title": "SYNTHETIC source text for validator testing"}],
        "change_records": [{
            "sequence": 1,
            "action": "created_synthetic_fixture",
            "description": "Created only for executable contract and adversarial-validator testing.",
        }],
    }


def decoy_review() -> Dict[str, Any]:
    return {
        "schema": "decoy-review/v1",
        "case_id": CASE_ID,
        "semantic_correctness_not_proven": True,
        "reviewer": "synthetic-example",
        "field_reviews": [
            {
                "field_id": "syn_response",
                "verdict": "pass",
                "decoys_checked": ["wrong_subject", "wrong_condition", "wrong_comparator", "same_number_elsewhere", "hedge_promotion"],
                "observation": "The quote binds SynA, condition C, comparator D, mean ± SD, 12.4, and nM in one synthetic sentence.",
            },
            {
                "field_id": "syn_unmeasured",
                "verdict": "pass",
                "decoys_checked": ["false_absence", "similar_field_substitution"],
                "observation": "All three synthetic paragraphs were inspected; none contains the requested second response measurement.",
            },
        ],
        "claim_reviews": [{
            "claim_id": "synthetic-claim-1",
            "verdict": "pass",
            "decoys_checked": ["hedge_promotion"],
            "observation": "Speculation and the words suggest/may remain attached to the claim.",
        }],
    }
