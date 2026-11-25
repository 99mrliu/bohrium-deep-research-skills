# Negative test

The synthetic fixture deliberately asserts a motor-to-rotor connection although the source only says that a rotor is above a chamber and no motor connection is described. This is a factual unsupported connection, not a formatting error.

Run:

```bash
python3 /path/to/source-span-atlas/tests/run_negative.py --output-dir /app/work/source-span-negative
```

The wrapper succeeds only when the validator returns nonzero, emits `UNSUPPORTED_ASSERTION`, records a failed verdict, and writes no `figure.svg`. Assertion failure is therefore expected inside the tested command and success for the wrapper. Output remains outside the Skill bundle.
