# Legacy Entry Points

BidFlow CLI is the preferred public interface for new users:

```powershell
bidflow market generate --scenario medium --output ./my_market
bidflow session run --market ./my_market --population "background=behavioral" --output ./outputs/baseline
bidflow replay run --baseline ./outputs/baseline --focal S001 --agent cass --data-dir ./my_market --output ./outputs/replay
```

The old `python -m src.*` commands remain supported as compatibility entry points. They are useful for reproducing historical reports and for development while the new package is still a façade over the proven runner/backtest code.

## Compatibility Mapping

| Legacy command | BidFlow CLI |
| --- | --- |
| `python -m src.data_generation.generate_synthetic_mvp --scenario ...` | `bidflow market generate --scenario ... --output ...` |
| `python -m src.data_generation.audit_synthetic_dataset --data-dir ...` | `bidflow market validate ...` |
| `python -m src.experiments.run_single_round_mvp ...` | `bidflow session run ...` |
| `python -m src.analysis.cass_focal_backtest ...` | `bidflow replay run --agent cass ...` |
| `python -m src.analysis.llm_focal_backtest ...` | `bidflow replay run --agent llm ...` |

## Cleanup Policy

- Do not delete legacy modules until the BidFlow CLI has parity tests for the corresponding workflow.
- Do not move generated data or experiment outputs into source control.
- Keep CSV schemas and old output filenames stable; BidFlow adds metadata files instead of replacing existing files.
- Temporary local scripts should either be promoted into `scripts/` with documentation or remain untracked.
