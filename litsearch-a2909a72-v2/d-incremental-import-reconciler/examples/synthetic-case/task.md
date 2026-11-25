# SYNTHETIC example task (not an organizer case)

A prior organizer-local import state (`import_state.json`) already holds two
records of a living literature library. A new Crossref snapshot page has arrived
under `snapshots/`. Reconcile the snapshot against the prior state: import what
is new, apply what is a legitimate metadata update, skip what is already
imported unchanged, and queue identity conflicts for human resolution instead of
merging them silently. Prove the import is idempotent by running the same pool
against the updated state a second time.
