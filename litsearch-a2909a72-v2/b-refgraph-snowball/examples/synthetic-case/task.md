# SYNTHETIC example task (not an organizer case)

Starting from the seed DOI in `case.json`, snowball over the local reference
graph contained in the Crossref-shaped snapshots under `snapshots/`: collect
backward hits (references of the seed that resolve locally) and forward hits
(local records citing the seed) up to 2 hops. Rank candidates with the
documented deterministic graph score, keep per-record provenance, and ledger
every reference that cannot be resolved locally.
