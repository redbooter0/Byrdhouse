# ByrdCoder Security Review

Security posture of ByrdCoder Local V0 (docs/BYRDCODER_LOCAL.md) against the
agent safety policy (docs/agent-safety-policy.md). Reviewed 2026-07-16 at
implementation time; re-review on any OpenCode/bridge upgrade.

## Threat model

An LLM-driven agent with tool access can, if unconstrained: write to
protected branches, exfiltrate secrets or personal identity data, damage the
production ComfyUI environment, run destructive shell commands, or silently
push unreviewed code. Local models make this cheaper to run, not safer —
the same guardrails apply as for cloud agents.

## Enforcement map — every prohibition, and WHAT enforces it

| Prohibition | Config (opencode) | Wrapper (scripts) | Verified by |
|---|---|---|---|
| Never write to `main` | byrd-build bash denies `git checkout/switch main*`; global edit deny outside byrd-build | start-byrdcoder.ps1 refuses byrd-build on protected branches / detached HEAD / non-approved prefixes | test-byrdcoder.ps1 guard tests; integration-suite contract checks |
| No YOLO/full-auto | Global permission deny-by-default; no profile grants blanket bash | Launcher only starts named profiles; default byrd-ask | contract checks (global deny) |
| No secret access | — (path-level denial is not an OpenCode permission primitive) | Prompts forbid `.env`/`secrets/`/`credentials/`/`db/`; allowlist.json names them; **founder rule: secrets stay out of the repo tree anyway (.env gitignored, admin_token placeholder)** | test-byrdcoder.ps1 forbidden-dirs check; secret-scan CI job on every push |
| No unnecessary identity-reference reads | Prompts (all profiles) forbid `profiles/*/references/` | allowlist.json forbidden dirs | contract checks |
| No deletions outside a disposable workspace | No profile allows `rm`/`del`/`Remove-Item`; bash `*` deny | Benchmark runs in a disposable clone under `logs\`; only there does the harness itself reset/clean | allowlist deny checks |
| No arbitrary PowerShell | `powershell`/`pwsh`/`cmd` in the deny list; bash `*` deny catchall in every profile | Launcher never passes through commands | contract checks |
| No production ComfyUI changes | `Generators/ComfyUI` in forbidden dirs; no profile can write there (edit allow is byrd-build only, prompts scope it to repo code dirs) | ByrdCoder has no ComfyUI adapter at all — it cannot reach port 8188 (webfetch denied, no HTTP tool) | contract checks |
| No push/merge without approval | `git push*`/`git merge*` denied in byrd-build; absent from every allow list | Promotion documented as founder-only Tier 4 | contract checks (no escape hatches in allow list) |
| No remote providers / data exfiltration | Only the `lmstudio` provider exists in the config; `share: disabled`; `webfetch: deny` globally and per profile; `autoupdate: false` | byrd-offline/byrd-private prompts refuse external routing; OPENCODE_CONFIG isolation keeps the founder's global config (which may hold cloud keys) out of scope | contract checks (share/autoupdate/webfetch/placeholder) |

## Defense in depth, honestly assessed

- **Layer 1 — config**: OpenCode permission blocks are the primary gate.
  They are enforced by the OpenCode runtime, not by the model.
- **Layer 2 — wrapper**: branch guard + isolated `OPENCODE_CONFIG` +
  gitignored machine config are enforced by our scripts.
- **Layer 3 — prompts**: path taboos (secrets/identity refs) are POLICY,
  not mechanism — a misbehaving model could still read a repo file its
  tools can reach. This is why secrets are never in the repo tree at all
  (the real Layer 0), the CI secret-scan runs on every push, and reference
  photos are gitignored so they simply do not exist in a fresh clone.
- **Layer 4 — review**: the two-agent loop fails closed (unparseable or
  unreachable reviewer = block), and nothing is promoted without the
  founder.

## Residual risks (accepted for V0, tracked)

1. **Prompt-injection via repo content**: a malicious string inside a file
   the agent reads could try to steer it. Mitigation: deny-by-default
   permissions bound the blast radius (worst case in byrd-ask is a wrong
   answer); byrd-build is used on feature branches with founder review.
2. **OpenCode/bridge supply chain**: `opencode-ai` (npm) and
   `opencode-lmstudio@0.3.1` are third-party code running with user rights.
   Mitigation: version pinned; `autoupdate: false`; upgrades are a logged
   founder decision; the plugin is MIT and small enough to skim before
   upgrading.
3. **Permission-pattern semantics**: bash allow/deny patterns are matched by
   OpenCode; an unexpected matching quirk could over-allow. Mitigation: the
   `"*": "deny"` catchall in every profile; on-machine `test-byrdcoder.ps1`
   before first real use; treat the acceptance checkpoint's step 8 (nothing
   touched main/secrets/ComfyUI) as the real proof.
4. **Local model quality**: a weak model can produce plausible-wrong code.
   Mitigation: Phase 5 benchmark gates the primary model choice; the
   two-agent loop reviews patches; tests are in the loop by design.
5. **LM Studio server exposure**: the LM Studio port serves the tailnet.
   Existing rule stands — nothing public, tailnet only; do not add
   listen-on-0.0.0.0 without policy review.

## Explicitly rejected in V0

- Codex proxy (optional adapter later, isolated lab, after the checkpoint).
- LM Studio "unlocked backend" patches and any tool granting the agent
  ComfyUI, router-admin, or dashboard-token access.
- Any full-auto mode against `E:\ByrdHouse` or `D:\ByrdHouse`.
