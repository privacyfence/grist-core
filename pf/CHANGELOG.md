# Changelog of the PrivacyFence fork

Changes to the fork itself (its build, release and checks). Upstream changes are in Grist's own release notes.

## [Unreleased]

### Fixed

- **Start on a fresh volume with personal orgs or site creation turned off.** With `GRIST_PERSONAL_ORGS=false` or `GRIST_ORG_CREATION_ANYONE=false`, Grist exited at its first start on an empty `/persist` with `Error: No example workspace available`. The internal support user now always gets its own (hidden) org, so startup succeeds. Volumes left by the failed start recover on the next start. A patch on upstream; see `pf/PATCHES.md`.

### Added

- **Lock-out check, pass 2.** The lock-out check also runs Grist with `GRIST_PERSONAL_ORGS=false` and `GRIST_ORG_CREATION_ANYONE=false` on a fresh `/persist` volume, then again after a restart on the same volume. It checks that a signed-in user sees only the team site, has no personal org, and cannot create a site.

## [1.7.22-pf.2] - 2026-10-31

### Added

- **Open-source image.** `ghcr.io/privacyfence/grist-core`, built from grist-core with no full-edition extensions, the full-edition switch off and every base image pinned by digest, for amd64 and arm64, with build provenance.
- **Lock-out check.** Every build signs in through OIDC, creates an API key and uses it, and checks the boot key, the team-site access API and the free plan's limits; a build where any of them is locked fails and cannot be merged or released.
- **Upstream sync.** A weekly workflow opens a pull request for each new upstream release, listing any upstream workflow it brings.
