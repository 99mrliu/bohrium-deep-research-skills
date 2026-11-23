# Source-forensics checklist (run order)

1. Inventory: list every file under `/input` with byte size and SHA-256
   (`scripts/forensic_scan.py`). Never skip the hash: it is the anchor that
   lets reviewers re-verify that the analyzed bytes are the provided bytes.
2. XML well-formedness: parse with a real XML parser, record error
   line/column verbatim. Do not regex-pretend a parse.
3. Salvage: if malformed, extract `<math>` fragments with byte offsets; mark
   every salvaged item `salvaged_fragment` and degrade the case status.
4. Structure statistics: count `mfrac/msub/msup/msubsup/msqrt/mtable/mfenced`
   per document; a formula catalog with zero structural features but complex
   alttext is a red flag (flattened copy, not real MathML).
5. Identity: match every `source-formulas.xml` node to a `publisher-source.xml`
   node by `id` AND structural signature. `id_absent` or `divergent` entries
   are findings, not noise.
6. Layer agreement: alttext TeX vs MathML feature multiset per formula;
   numeric constants in XML prose vs PDF text layer. Report both sides of any
   disagreement.
7. Status law: success requires all layers clean; partial for salvage,
   divergence, or skipped layers; insufficient_evidence when no
   formula-bearing artifact exists.
8. Handoff: downstream transcription/derivation/numeric work may only rely on
   formulas listed in the verified inventory; others carry their degraded
   status forward.
