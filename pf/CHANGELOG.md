# Changelog of the PrivacyFence fork

Changes to the fork itself (its build, release and checks). Upstream changes are in Grist's own release notes.

## [Unreleased]

### Added

- **Open-source image.** `ghcr.io/privacyfence/grist-core`, built from grist-core with no full-edition extensions, the full-edition switch off and every base image pinned by digest, for amd64 and arm64, with build provenance.
- **Lock-out check.** Every build signs in through OIDC, creates an API key and uses it, and checks the boot key, the team-site access API and the free plan's limits; a build where any of them is locked fails and cannot be merged or released.
- **Upstream sync.** A weekly workflow opens a pull request for each new upstream release, listing any upstream workflow it brings.
