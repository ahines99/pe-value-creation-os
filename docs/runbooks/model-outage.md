# Model provider outage

**Signals:** runs paused with `pause_reason = model_unavailable`; `PvcModelUnavailable`.

1. Confirm on the provider's status page and in worker logs: `model_call` events stop; pause reasons show RateLimitError, APIConnectionError, HTTP 5xx or refusal.
2. The operating partner chooses:
   - **Wait:** resume paused runs after recovery with `pvc resume <run_id>`. Diagnostics re-run; nothing is guessed.
   - **Switch to rules temporarily:** set `model.on_unavailable = "rules"` in `policy.toml`, bump the policy version and deploy. Proposals are then rule-based and labelled `rules(fallback)` in the run artifacts.
3. Revert the policy change after recovery.
