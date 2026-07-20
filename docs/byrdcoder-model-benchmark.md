# ByrdCoder Model Benchmark

Phase 5 of docs/BYRDCODER_LOCAL.md. Every coding-capable model currently
installed in LM Studio runs the SAME 7-task protocol via
`scripts\byrdcoder-benchmark.ps1`; the primary ByrdCoder model is chosen from
this table, **never from subjective chat quality**. Do not download new
models until the installed ones are measured. Load one candidate at a time in
LM Studio so VRAM/RAM numbers are honest on the 8 GB card.

## The 7 tasks (identical wording per model — the runner owns the text)

1. **Explain** `scripts/byrdcast_swap.py` (byrd-ask).
2. **Find one real bug** without modifying the file (byrd-ask).
3. **Produce a patch** for that bug — unified diff, must `git apply` (byrd-patch).
4. **Apply + regression test** on the bench feature branch, in the
   disposable clone (byrd-build).
5. **Run the applicable test** and report honestly (byrd-test).
6. **Review its own patch** for risks, verdict JSON (byrd-review).
7. **Summarize changed files and rollback** (byrd-ask).

## Metrics

Measured by the runner: task wall time, exit code, VRAM after task
(nvidia-smi), system RAM used, applied diff + commit list per model.

Judged from the transcripts (score 0–2 each: 0 fail / 1 partial / 2 clean):

- successful tool calls (did file reads/greps/commands actually run)
- correct file paths (no invented paths)
- patch applicability (`git apply --check` on task 3's diff)
- test success (task 5 truly ran and reported the real result)
- hallucinated functions/files (count; any hallucination caps the task at 0)
- context reliability (later tasks still consistent with earlier facts)
- recovery (after a failed command, did it correct course or spiral)

## How to run

```powershell
# everything discovered as coder-family:
powershell -ExecutionPolicy Bypass -File scripts\byrdcoder-benchmark.ps1
# explicit candidates + cross-model review:
powershell -ExecutionPolicy Bypass -File scripts\byrdcoder-benchmark.ps1 -Models "<qwen-coder-id>","<qwopus-id>" -Reviewer "<other-model-id>"
```

Outputs land in `logs\byrdcoder\bench_<stamp>\`: per-model transcripts,
`applied.diff`, `commits.txt`, `bench.json`, and `benchmark.md` (the table
skeleton with measured columns pre-filled). Fill the judgment columns from
the transcripts and paste the finished table below. Repeat runs before
declaring a primary model.

## Results

*(no runs recorded yet — paste finished benchmark tables here, newest first,
with the exact model ids tested and the bench folder path)*

## Primary model decision

*(pending benchmark — record the chosen primary + reviewer pair and the
date/table that justified it, then log the decision in DECISIONS.md)*
