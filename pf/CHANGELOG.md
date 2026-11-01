# Changelog of the PrivacyFence fork

Changes to the fork itself (its build, release and checks). Upstream changes are in Grist's own release notes.

## [Unreleased]

## [1.7.22-pf.4] - 2026-11-01

### Fixed

- **The boot key is no longer written to the logs.** Grist printed `GRIST_BOOT_KEY` at every start, twice: in the `BOOT KEY: ...` banner and in the settings dump (`== grist.boot.key: ...`). A key from `GRIST_BOOT_KEY` now shows the banner `Boot key: set by GRIST_BOOT_KEY` without the value, and the settings dump shows `*****`. The key still works at `/boot` and in the `x-boot-key` header. A key that does not come from the environment is shown as before. A patch on upstream; see `pf/PATCHES.md`.

### Added

- **Lock-out check: no secret in the logs.** The lock-out check starts Grist with distinctive values for the boot key, the session secret and the OIDC client secret, and fails every pass (fresh start and restart) if any of them appears in the container's output.

## [1.7.22-pf.3] - 2026-11-01

### Fixed

- **Start on a fresh volume with personal orgs or site creation turned off.** With `GRIST_PERSONAL_ORGS=false` or `GRIST_ORG_CREATION_ANYONE=false`, Grist exited at its first start on an empty `/persist` with `Error: No example workspace available`. The internal support user now always gets its own (hidden) org, so startup succeeds. Volumes left by the failed start recover on the next start. A patch on upstream; see `pf/PATCHES.md`.

### Added

- **Lock-out check, pass 2.** The lock-out check also runs Grist with `GRIST_PERSONAL_ORGS=false` and `GRIST_ORG_CREATION_ANYONE=false` on a fresh `/persist` volume, then again after a restart on the same volume. It checks that a signed-in user sees only the team site, has no personal org, and cannot create a site.

## [1.7.22-pf.2] - 2026-10-31

### Added

- **Open-source image.** `ghcr.io/privacyfence/grist-core`, built from grist-core with no full-edition extensions, the full-edition switch off and every base image pinned by digest, for amd64 and arm64, with build provenance.
- **Lock-out check.** Every build signs in through OIDC, creates an API key and uses it, and checks the boot key, the team-site access API and the free plan's limits; a build where any of them is locked fails and cannot be merged or released.
- **Upstream sync.** A weekly workflow opens a pull request for each new upstream release, listing any upstream workflow it brings.
