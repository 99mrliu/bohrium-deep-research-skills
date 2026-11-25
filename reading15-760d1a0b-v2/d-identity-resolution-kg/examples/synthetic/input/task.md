# Task brief — SYNTHETIC example, not real papers.

Build a small knowledge graph over the two synthetic papers in this input directory
(S1 = primary, S2 = secondary). The focus of this bundle is cross-paper identity
resolution:

1. Discover the input files, normalize the corpus, and let the scripts generate
   candidate alias pairs deterministically.
2. Adjudicate every candidate pair (merge / nonmerge with a one-line reason and
   evidence paragraph ids). The TiO2 mentions in the two papers refer to different
   physical layers and must remain an explicit NON-merge.
3. Extract a small set of typed nodes, edges and numeric claims, each with an exact
   verbatim quote from the cited paragraph.
4. Keep the two PCE claims (21.1% initial vs 18.7% after damp-heat aging) as two
   separate claims linked in the conflict registry; do not average or merge them.
5. Record that the hysteresis index was not reported.
6. Execute the 3 query_specs from case.json and assemble result.json mirroring the
   declared output_contract keys.

This is a SYNTHETIC example corpus; the papers are invented and any resemblance to
real results is coincidental.
