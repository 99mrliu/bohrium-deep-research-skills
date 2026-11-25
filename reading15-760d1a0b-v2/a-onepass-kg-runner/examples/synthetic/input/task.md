# SYNTHETIC example task (not a real challenge task)

> SYNTHETIC example, not real papers. This brief exists only to exercise the
> a-onepass-kg-runner pipeline end to end.

Build a knowledge graph from the two SYNTHETIC mini-papers (P1 primary, S1
secondary) on perovskite solar cells. Every node and edge must cite
`source_id` + JATS `paragraph_id` + a verbatim quote that is an exact substring
of the cited paragraph. Handle the cross-paper alias "methylammonium lead
iodide" (P1) vs "MAPbI3" (S1), keep the numeric PCE conflict (21.1% initial vs
18.7% retained after damp-heat) as separate claims under different conditions,
do NOT merge the two different TiO2 layers, record the unreported hysteresis
index, and answer the three query_specs declared in case.json.
