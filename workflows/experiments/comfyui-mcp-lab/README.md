# ComfyUI MCP Workflow Lab (Role B sandbox)

Working directory for the **Isolated Workflow Architect**
(`comfyui-mcp@0.34.0`, pinned — see `configs/byrdcoder/comfyui-mcp-lab.env.example`
and docs/BYRDCODER_COMFY_MCP.md). The architect edits graphs HERE and only
here.

Rules:

1. **Copies only.** Never edit a file in the parent `workflows/` directory.
   Copy it in first: `Copy-Item workflows\<name>.json workflows\experiments\comfyui-mcp-lab\`
2. **Isolated ComfyUI only.** The lab server points at the Workflow Lab
   instance, never production `byrd-gaming:8188`. If the lab instance is not
   running, the architect stays read-only against saved JSON.
3. **Read-only first.** Until the read-only verification pass is recorded in
   docs/BYRDCODER_COMFY_MCP.md, the architect inspects/summarizes/diagnoses
   only — no graph edits.
4. **No installs, no downloads, no restarts, no tunnels, no publishing,
   no deletion of files outside this folder.** Those capabilities are denied
   in the lab environment config.
5. Experiment files here are disposable and reviewable; promising graphs move
   to `workflows/candidates/` **only** through the 7-gate checklist in that
   folder's README — never automatically.
