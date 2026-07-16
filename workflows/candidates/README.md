# Workflow Candidates — promotion gate

Staging area between the Workflow Lab
(`workflows/experiments/comfyui-mcp-lab/`) and the production `workflows/`
directory. A graph may be COPIED here **only after every gate below passes**,
and promotion out of here into production is a founder decision.

## The 7 gates (all required, in order)

1. **JSON validation** — `python -m json.tool <file>` clean; API-format graph
   (numbered nodes with `class_type` + `inputs`).
2. **Required-node validation** — every `class_type` exists on the target
   ComfyUI (core or an installed, license-cleared custom node); verify via
   the belt's `/comfy/nodes` route or `facelab_preflight.py`.
3. **Dry-run / isolated generation** — the graph completes on the Workflow
   Lab instance (or a mock) without errors.
4. **Visual review** — the founder has looked at the output and accepts it.
5. **Dependency + license manifest** — any new node pack or model has its row
   in `docs/model-license-manifest.md` (license, lane, size/hash, rollback)
   BEFORE the candidate lands here.
6. **Rollback documentation** — the candidate file records (in a `_comment`
   or companion note) what to delete/revert to undo it.
7. **Founder approval** — recorded in `docs/DECISIONS.md` when the candidate
   is promoted to production `workflows/`.

Nothing in this folder is executable by the byrd-comfy executor — only
entries curated into `configs/byrdcoder/approved_workflows.json` run, and
that file only references graphs that have completed all seven gates.
