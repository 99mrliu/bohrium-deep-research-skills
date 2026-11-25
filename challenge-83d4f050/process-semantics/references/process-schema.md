# SBGN-inspired process schema

All included fixtures are **SYNTHETIC — NOT A SCIENTIFIC CLAIM**. This model borrows visual concepts from SBGN but is not an SBGN XML exchange implementation.

## Model

```json
{
  "entities": [{
    "canonical_id": "kinase-inactive",
    "label": "Kinase K",
    "layout": {"x": 70, "y": 230, "w": 210, "h": 70}
  }],
  "processes": [{
    "process_id": "activate-k",
    "process_type": "activation",
    "inputs": ["kinase-inactive"],
    "outputs": ["kinase-active"],
    "modulators": [{"entity_id": "receptor-r", "effect": "activation"}],
    "source_locator": {"document": "curated-source-id", "locator": "exact figure/panel"},
    "layout": {"x": 410, "y": 250}
  }]
}
```

Every entity needs a safe unique `canonical_id` and a nonempty display `label`; `compartment` is optional except where transport consistency is checked. Every process needs a safe unique `process_id`, a supported `process_type`, explicit `inputs`, `outputs`, and `modulators` lists, and a source locator. At least one input or output is required. All input, output, and modulator entity IDs must exist.

Processes are nodes, not anonymous edge labels. Their glyphs are `ASSOC`, `DISSOC`, `P`, `U`, `T`, `Tx`, `+`, `INH`, and `?` for association, dissociation, phosphorylation, ubiquitination, transport, transcription, activation, inhibition, and uncertain respectively.

## Arc semantics

- `inputs` are consumed molecular/state pools and produce solid gray **consumption** lines with filled arrowheads into the process node.
- `outputs` are produced molecular/state pools and produce solid blue **production** lines with filled arrowheads out of the process node.
- `modulators` are objects `{entity_id, effect}`. `activation` is a hollow green stimulation arrow into the process node; `inhibition` is a red perpendicular **T-bar** into the process node; `uncertain` is dashed purple with a question-mark endpoint.
- Arcs target process nodes. Roles cannot be swapped as a layout convenience. The visible marker is chosen from `arc_class`/`effect`, never from an entity's name.
- An association record creates only association semantics and its declared consumption/production arcs. It does not automatically add stimulation, modification, activity, or any extra edge.
- Direction, stimulation, and modification remain separate fields. Do not encode “activates” by reversing a production arc or encode “phosphorylates” as a stimulation arrow.

For an `activation` process, inactive and active states may be explicitly separate input/output entities, so a filled production line remains distinct from a receptor's hollow modulation arrow. For an `inhibition` process, outputs must be empty, while at least one input or an output is still required. Hence a valid inhibition-only test process has an explicit input and no production arrow. Any output on an inhibition process raises `INHIBITION_PRODUCTION` before rendering.

## Transport

Transport requires at least one input and output plus nonempty `from_compartment` and `to_compartment`. Normalized names must differ. If input/output entities declare a compartment, those values must equal the origin/destination respectively (NFKC, whitespace, and case-insensitive comparison). This catches reversed endpoints, same-compartment pseudo-transport, and mismatched state pools.

## Audit and content map

`semantic-audit.json` lists every issue and unknown endpoint and counts consumption, production, activation modulation, inhibition modulation, and uncertain modulation arcs separately. `content-map.json` joins SVG entity/process IDs back to the full semantic fields and lists every planned arc with its class/effect. No success status implies that the curated source assertions are biologically correct.
