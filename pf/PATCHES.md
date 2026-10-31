# Recorded patches and declined upstream changes

Upstream files change only as patches recorded here.

## Patches

| Commit on `privacyfence` | Upstream file | Why | Upstream issue or PR | Can be dropped when |
| --- | --- | --- | --- | --- |

## Declined upstream changes

| Upstream release | What it gates or removes | What was done |
| --- | --- | --- |

## Rule

- **A gating change.** A sync PR whose lock-out check fails is never merged as is. If the cause is one gating change, a revert commit of exactly that change goes on the sync branch, and is recorded.
- **A removal.** If upstream *removes* a feature the check needs (for example OIDC), the fork stays on its last good release. An issue records it, and whether to carry a re-add patch is the maintainer's decision.
