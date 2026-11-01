# Recorded patches and declined upstream changes

Upstream files change only as patches recorded here.

## Patches

| Commit on `privacyfence` | Upstream file | Why | Upstream issue or PR | Can be dropped when |
| --- | --- | --- | --- | --- |
| `576b41c`, `204cbda` | `app/gen-server/lib/homedb/UsersManager.ts` | With `GRIST_PERSONAL_ORGS=false` or `GRIST_ORG_CREATION_ANYONE=false`, a fresh home database gets no org for the support user, and startup fails with `No example workspace available` (`HomeDBManager.initializeSpecialIds`). The patch always creates the support user's personal org; with personal orgs disabled it stays hidden from users. The suite sets both settings. | None filed yet (upstream v1.7.22 and `main` have the bug). | Upstream creates the support user's workspace with personal orgs disabled; pass 2 of the lock-out check passes without the patch. |
| _this PR_ | `app/server/lib/FlexServer.ts`, `app/server/lib/gristSettings.ts` | Grist printed the boot key from `GRIST_BOOT_KEY` in its startup banner (`addSetupGate`) and in the settings dump (`summary`, `grist.boot.key`), so it reached `docker logs` and log collectors. The banner now names the source instead of the value when the key comes from the environment; the `boot.key` setting is `censor`ed so the dump shows `*****`. | None filed yet. Upstream `main` has the same code. | Upstream stops printing an operator-supplied boot key and censors `grist.boot.key`; the lock-out check's log check passes without the patch. |

## Declined upstream changes

| Upstream release | What it gates or removes | What was done |
| --- | --- | --- |

## Rule

- **A gating change.** A sync PR whose lock-out check fails is never merged as is. If the cause is one gating change, a revert commit of exactly that change goes on the sync branch, and is recorded.
- **A removal.** If upstream *removes* a feature the check needs (for example OIDC), the fork stays on its last good release. An issue records it, and whether to carry a re-add patch is the maintainer's decision.
