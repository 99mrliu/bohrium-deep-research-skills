# Audience model and adaptation levers

Fill `/app/work/audience.json` before choosing a spine. Every field must be traceable to the work order; where the work order is silent, state an assumption and mark it `assumed: true`.

## Schema

```json
{
  "audience_label": "as stated in the work order",
  "decision": "one checkable sentence: what they should know/believe/decide afterwards",
  "prior_knowledge": {"assumed": ["..."], "must_explain": ["..."]},
  "objections": [{"question": "...", "answered_by": "slide N | backup M | none-accepted-risk"}],
  "levers": {
    "background_share": "0-40% of content slides",
    "terminology_scope": "what gets defined on-slide",
    "evidence_depth": "headline-only | key numbers | full controls",
    "conclusion_position": "first | last"
  }
}
```

## Default profiles (override with the actual work order)

| Audience | Assumed knowledge | Must explain | Background share | Evidence depth | Conclusion |
|-|-|-|-|-|-|
| Own group / advisor | project, methods, notation | nothing project-internal | ~0% | key numbers + what failed | early (plan vs actual) |
| Thesis/defense committee | field basics, not your problem | problem setting, why gap is real | 20–30% | full controls for key claims | last (earned) |
| Conference (specialist) | field methods | your specific problem variant | 10–15% | one result in depth | last |
| Reviewers / panel | domain goals, not technique | method credibility in one slide | ~10% | numbers with conditions | first |
| Cross-disciplinary | none of the field | all terms, worked example | 30–40% | headline + one concrete case | first and last |

## Objection anticipation

Derive likely objections from the audience's role, not generic lists:

- Committee: "is the gap real / is the validation adequate / what exactly is the contribution".
- Advisor/group: "why is X stuck / what changed vs the plan / what do you need".
- Reviewers: "what is the evidence strength / what is the risk / why you".
- Specialists: "how does this differ from <the standard approach> / what about <known hard case>".

Each objection must map to a planned slide, a backup, or an accepted risk recorded in `audience.json`. An objection with no answer plan is a storyboard defect.

## Duration discipline

- Slides that present evidence need 60–120 s each; framing slides 30–45 s. If `duration / slide_count` is far outside this, the count or the content density is wrong — fix the plan, not the delivery speed.
- Reserve mandated Q&A time before allocating speaking minutes.
- In the storyboard, no single slide may exceed 20% of total speaking time unless it is the designated key-result slide.
