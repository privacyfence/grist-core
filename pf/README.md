# PrivacyFence fork of grist-core

## What this is

`privacyfence/grist-core` builds and releases its own Grist image from the open-source code only. The `privacyfence-suite` stack and grist-provisioner then never depend on a Grist build that can lock a feature behind a paid edition (OIDC sign-in, the boot key, the team-site access API, API keys, the free plan's limits). Our files live under `pf/`, `.claude/` and `.github/workflows/pf-*.yml`; upstream files change only as recorded in [PATCHES.md](PATCHES.md).

## Image

`ghcr.io/privacyfence/grist-core`, tagged `X.Y.Z-pf.N` and `latest`.

## Branches and rulesets

- `privacyfence` is the default branch. It holds upstream's latest release tag (named in `pf/UPSTREAM`) plus our files and recorded patches. Releases are cut only from it. Its ruleset requires a pull request and the passing check `image-and-lockout`.
- `main` is an untouched mirror of upstream `main`, updated with "Sync fork". Nothing uses it.
- Release tags are `vX.Y.Z-pf.N`: `X.Y.Z` equals `package.json`'s `version`, `N` counts our releases on it, starting at 1. A tag ruleset lets only admins create `v*-pf.*` tags.

## Release

Only the maintainer releases, and only from `privacyfence`.

1. Open a PR to `privacyfence` that adds a `## [X.Y.Z-pf.N] - YYYY-MM-DD` section to `pf/CHANGELOG.md` (move the entries from `## [Unreleased]` into it). `X.Y.Z` must equal `package.json`'s `version`; `N` is 1 for the first release on that version. The section's body becomes the release notes, after the line `Built from gristlabs/grist-core vX.Y.Z.`. Merge it once `image-and-lockout` is green.
2. Tag the merge commit and push the tag:

   ```sh
   git fetch origin privacyfence
   git tag vX.Y.Z-pf.N origin/privacyfence
   git push origin vX.Y.Z-pf.N
   ```

   The tag push is the only thing that publishes; `pf-release.yml` run any other way is a dry run. Its `check` job fails the release unless the tag looks like `vX.Y.Z-pf.N`, `X.Y.Z` equals `package.json`'s `version`, the tagged commit is on `privacyfence`, and `pf/CHANGELOG.md` has a `## [X.Y.Z-pf.N]` section.
3. The workflow builds amd64 and arm64, pulls the exact amd64 image it pushed and runs the lock-out check on that digest, then creates the manifest list (`X.Y.Z-pf.N` and `latest`), attests build provenance and creates the GitHub release. It also copies the gvisor base image to `ghcr.io/privacyfence/gvisor-unprivileged:buster`.
4. The first time only: in GitHub, open the organisation's Packages, and make `grist-core` and `gvisor-unprivileged` public (Package settings, Danger Zone, Change visibility). A package that stays private cannot be pulled by the suite, and the gvisor fallback needs the copy to be public.
5. Check the release:

   ```sh
   gh attestation verify oci://ghcr.io/privacyfence/grist-core:X.Y.Z-pf.N --repo privacyfence/grist-core
   ```

To rehearse a release without publishing, run `pf-release.yml` from the Actions tab (`workflow_dispatch`; it also runs by itself on pull requests that touch it). A dry run builds both architectures and runs the lock-out check on amd64.

## Upstream sync

`pf-sync.yml` runs every Monday at 06:23 UTC and on demand. It finds the newest upstream release tag (`vX.Y.Z`, no pre-releases), and stops quietly if `pf/UPSTREAM` already names it, if the branch `sync/vX.Y.Z` exists, or if an open issue `Upstream vX.Y.Z needs a manual merge` exists. Otherwise it merges the tag into a new branch `sync/vX.Y.Z`, writes the tag to `pf/UPSTREAM` and opens the PR `Merge upstream vX.Y.Z`. If the merge conflicts, it opens the issue instead, listing the conflicting files; merge by hand on `sync/vX.Y.Z`, record the patches in [PATCHES.md](PATCHES.md), and write the tag to `pf/UPSTREAM`.

Review a sync PR with this checklist:

- [ ] `image-and-lockout` is green. If it is red, never merge as is: follow the rule in [PATCHES.md](PATCHES.md) (revert exactly the gating change and record it, or, if upstream removed a feature the check needs, stay on the last good release and record it in an issue).
- [ ] The PR body lists the upstream workflow files the merge added or changed. Merging adds them to the repository, where they would run. For each new or changed upstream workflow other than `pf-*.yml`, open the Actions tab and disable it before merging. Upstream workflows are never deleted: that would conflict with every later upstream change to them.
- [ ] Read upstream's release notes (linked in the PR) for anything that gates, moves or removes OIDC, the boot key, the team-site access API, API keys or the free plan's limits.
- [ ] Check [PATCHES.md](PATCHES.md): does a recorded patch need updating, or can it be dropped?
- [ ] Merge (merge commit), then release as above if you want the new version.

`pf-sync.yml` uses the repository secret `PF_SYNC_TOKEN`, a fine-grained personal access token limited to this repository, with Contents, Pull requests, Issues and Workflows set to read and write. It is needed because `GITHUB_TOKEN` cannot push the workflow changes a merge brings, and a PR it opens triggers no checks. The token expires. Before that date, create a new one with the same settings (GitHub, Settings, Developer settings, Fine-grained tokens), and replace the secret (repository Settings, Secrets and variables, Actions). If it has expired, the sync run fails at checkout.

GitHub disables scheduled workflows in a repository with no activity for 60 days. If the Actions tab shows `pf-sync` as disabled, open it and click "Enable workflow", then run it once with "Run workflow".

## Lock-out check

`bash pf/e2e/run_lockout.sh <image>` runs in `pf-ci.yml` (every push to `feature/**`, `fix/**`, `chore/**` and `sync/**`, and every PR to `privacyfence`) and in `pf-release.yml`. `image-and-lockout` is the required check of the `privacyfence` ruleset, so a failure can neither merge nor, because releases come from `privacyfence`, be released.

**Image report.** It fails, naming the item, unless the image has `GRIST_EXT_FULL_EDITION_BASE_URL=` (empty) and `GRIST_ALLOW_AUTOMATIC_VERSION_CHECKING=false` in its environment (`ok: image env`), and has no `/grist/ext/app`, `/grist/ext/assets` or `/grist/_build/ext`, and a build channel of `core` in `/grist/_build/app/common/version.js` (`ok: image contents`). A failure means full-edition code, or a switch to it, could be in the image: the build arguments or the dummy `ext/` changed, or upstream's `Dockerfile` or version file changed. Never remove the check; if only the compiled form of the channel changed, adjust the pattern in `run_lockout.sh` to whatever still shows the literal `core`.

It then starts the mock OIDC server and the image with the boot key in the environment only, and `pf/e2e/lockout_check.py` prints `ok: <name>` for each of six checks, stopping at the first `FAIL: <name>: <message>`:

| Check | What it proves | A failure means |
| --- | --- | --- |
| `boot_key_access` | `GET /api/orgs/team/access` with `x-boot-key` answers with a `users` list. | The boot key no longer reaches the install admin, or the team-site access API is gated. |
| `free_plan_limits` | The `team` site's product is `Free` and has none of `maxUsersPerOrg`, `maxApiCallsPerOrgMonth`, `baseMaxRowsPerDocument`. | The free plan acquired a limit, or the site is on another product. If only the JSON path changed, adjust the path; never remove the check. |
| `team_membership` | `PATCH /api/orgs/team/access` adds users, and they are listed as `editors`. | Adding members to the team site is blocked. |
| `oidc_sign_in` | A browser-like client signs in through the mock OIDC server and `GET /api/profile/user` returns the expected email. | OIDC sign-in was gated or removed, or the mock server behaves differently (read the mock's log). |
| `api_key` | A signed-in user can `POST /api/profile/apikey` and gets a 40-hex key. | API keys are gated. |
| `api_key_use` | That key can create a workspace and a document, and list its tables. | API-key authentication or document creation is gated. |

After the checks, the script fails if Grist's log mentions the full edition (`ok: logs`). Nothing it prints contains the boot key, an API key or a cookie; keep it so, and never add `set -x` to the script. A failing run prints both containers' logs.

## Pins

Both workflows build the unchanged `Dockerfile` with build contexts that replace each `FROM` line by a digest: `GVISOR_DIGEST`, `NODE_DIGEST` (`node:22-trixie`), `NODE_SLIM_DIGEST` (`node:22-trixie-slim`) and `PYTHON_DIGEST` (`python:3.11-slim-trixie`), plus `MOCK_OIDC_IMAGE` (with `MOCK_OIDC_TAG`, in `pf-ci.yml`) for the mock identity provider. The digests are those of the multi-arch index, and they are the same in `pf-ci.yml` and `pf-release.yml`.

The `digests` job of `pf-ci.yml` prints the current digest of each tag and fails if it differs from the pin. That is a reminder, not a defect: a base image was updated. To update a pin, change the same value in both workflows to the digest the job printed, in a PR; that PR's `image-and-lockout` run tests the new image. Pin changes are never automatic.

If the Dockerfile's `FROM` lines change in a sync, update the build contexts to match (the names must equal the `FROM` text).

## gvisor fallback

Each release copies the pinned gvisor image to `ghcr.io/privacyfence/gvisor-unprivileged:buster`. If `docker.io/gristlabs/gvisor-unprivileged` disappears, change the `docker.io/gristlabs/gvisor-unprivileged:buster=docker-image://…` line in the `build-contexts` of both workflows to `docker-image://ghcr.io/privacyfence/gvisor-unprivileged@${{ env.GVISOR_DIGEST }}`. The copy must be public (see Release, step 4), because the builds read it without a login; check this in the package settings now, not when the upstream image is gone.

## Testing patches

Our patches are not run through upstream's test suite, which runs only on `main`; the fork runs only the lock-out check. This gap is accepted. Smoke-test a patched release by hand in the suite before relying on it.

## Licence

Built from grist-core under Apache-2.0. This is not an official Grist release. Upstream's `LICENSE.txt` and `NOTICE.txt` are kept.
