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

1. Open a PR that adds a `## [X.Y.Z-pf.N] - YYYY-MM-DD` section to `pf/CHANGELOG.md`. Its body becomes the release notes, after the line `Built from gristlabs/grist-core vX.Y.Z.`.
2. After it merges, the maintainer pushes the tag `vX.Y.Z-pf.N`.
3. The first time, make the `grist-core` and `gvisor-unprivileged` packages public.
4. Check the release with `gh attestation verify`.

The details of this section are completed by a later phase of this plan.

## Upstream sync

What `pf-sync.yml` does, how to review its PR, new upstream workflows, `PF_SYNC_TOKEN`'s expiry and renewal, and re-enabling scheduled workflows (GitHub disables them after 60 days without activity, in the Actions tab) are completed by a later phase of this plan.

## Lock-out check

What each check proves and what a failure means are completed by a later phase of this plan.

## Pins

Base images are pinned by digest. `digests` shows drift; updating a pin is a PR. Completed by a later phase of this plan.

## gvisor fallback

Completed by a later phase of this plan.

## Testing patches

Our patches are not run through upstream's test suite, which runs only on `main`. Smoke-test a patched release by hand in the suite.

## Licence

Built from grist-core under Apache-2.0. This is not an official Grist release. Upstream's `LICENSE.txt` and `NOTICE.txt` are kept.
