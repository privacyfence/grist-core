# An operational PrivacyFence fork of grist-core

## Goal

`privacyfence/grist-core` builds and releases its own Grist image, `ghcr.io/privacyfence/grist-core`. The `privacyfence-suite` stack and grist-provisioner then never depend on a Grist build that can lock a feature behind a paid edition. That covers the OIDC sign-in the suite uses, the boot key, the team-site access API, API keys, and the free plan's limits.

The fork must:

1. **Build only the open-source code.** No full-edition extensions, no runtime download of them, and every base image pinned by digest.
2. **Change upstream as little as possible.** Our own files live under `pf/`, `.claude/` and `.github/workflows/pf-*.yml`. Upstream files change only as recorded patches.
3. **Prove at every build that nothing is locked.** A CI check signs in through OIDC and uses the APIs the suite needs. A change that gates them fails the build. Because of a branch ruleset, a failing build can neither merge nor be released.
4. **Take upstream releases only through a reviewed pull request,** opened automatically when upstream tags a release.

## Current state

- **The fork.** `privacyfence/grist-core` is a fresh fork. Its `main` is upstream's head (`aa1b8a1`), and it has no tags.
  - Upstream's latest release is `v1.7.22`, commit `a10b7227365adfe2555be40ae87bb9741284c0ca` ("v1.7.22 (#2729)"), which is in the fork's history.
  - This plan's branch is cut from that commit, and adds `.claude/toolkit.yaml` and `pf/CHANGELOG.md`.
- **Two upstream images, one Dockerfile.** The `Dockerfile` itself is not changed by this plan.
  - `FROM scratch AS ext` (`Dockerfile:7`) takes extensions from a build context. Upstream's `grist` image puts the closed `grist-ee` extensions there (`.github/workflows/docker.yml`, "Check out the ext/ directory"). `grist-oss` uses a dummy `ext/`.
  - Build arguments `GRIST_BUILD_CHANNEL` and `GRIST_BUILD_COMMIT` (`:55-58`) go to `yarn run build:prod`.
  - `GRIST_ALLOW_AUTOMATIC_VERSION_CHECKING` (default `false`) and `GRIST_EXT_FULL_EDITION_BASE_URL` (default `https://grist-static.com/grist-full-edition`) are runtime ARGs (`:100-101`) that become ENVs (`:187-188`).
  - The base images are `node:22-trixie` (`:13`), `python:3.11-slim-trixie` (`:74`), `docker.io/gristlabs/gvisor-unprivileged:buster` (`:91`) and `node:22-trixie-slim` (`:98`).
  - At runtime: user `grist` via `useradd` (`:159`), `WORKDIR /grist` (`:162`), entrypoint `["./sandbox/docker_entrypoint.sh"]` and command `["./sandbox/run.sh"]` (`:205-206`).
- **When a running Grist can switch itself to the full edition** (`app/server/lib/bootstrapFullEdition.ts`).
  - Only when the build's channel is `release` (`defaultIsReleaseBuild`, `:86-88`) and `GRIST_EXT_FULL_EDITION_BASE_URL` is not empty (`getBaseUrl`, `:96-102`).
  - `getFullEditionIdentity` (`:109-112`) returns undefined otherwise. That short-circuits every caller: `isExtFullEditionSupported`, `resolveFullEditionWorker` and `maybeManageFullEdition`.
  - The process environment wins over any value an admin stores (`AppSettings.ts:92-115`).
  - Built-in extensions are detected by `/grist/ext/app` (`defaultHasBuiltInExt`, `:77-79`).
- **How the channel is set.** `buildtools/build.sh` (`build_version_file`, `:30-56`) sets it from `GRIST_BUILD_CHANNEL`. Without that, a clean checkout of tag `v<version>` gives `release`, and anything else gives `core`. Docker builds have no `.git` (`.dockerignore` is a whitelist), so the build argument decides. The channel is written into `app/common/version.ts`, which compiles to `/grist/_build/app/common/version.js`.
- **What is gated today.**
  - The Admin panel shows OIDC and SAML as needing an activation key (`app/client/ui/AuthenticationSection.ts:103-105`). That is client-side only.
  - The server builds OIDC with no edition check (`app/server/lib/coreLogins.ts:44-48`, `loginSystemHelpers.ts:44-74`).
  - The README lists "Single sign-on (SSO) via OIDC or SAML (2026)" under "Features not in grist-core" (`README.md:139`). A future upstream release may *remove* OIDC rather than gate it.
- **The APIs the suite relies on.**
  - `POST /api/profile/apikey` (`app/gen-server/ApiServer.ts:566-573`) needs a signed-in user. It answers with the key as plain text: `randomBytes(20)` as hex, 40 characters (`UsersManager.ts:37-39`).
  - Cookie-authenticated writes must pass the CSRF rule (`Authorizer.ts:550-567`): `X-Requested-With: XMLHttpRequest`, or `Content-Type: application/json`.
  - An `x-boot-key` header maps to the install admin, and counts as explicit auth, so no CSRF header is needed (`Authorizer.ts:328-340`).
  - The `team` site is created by `setUpSingleOrg` with the admin as owner (`stubs/app/server/server.ts:137-167`). Its product is `Free`, through `GRIST_DEFAULT_PRODUCT` (`server.ts:28`, `Product.ts:169-182`).
- **Upstream workflows.**
  - `docker.yml` and `docker_latest.yml` push to Docker Hub.
  - `fly-*.yml` (four) run preview deployments.
  - `cla.yml` is the CLA bot.
  - `self-hosted.yml` writes to a Grist Labs project.
  - `translation_keys.yml` runs only for `gristlabs`.
  - `main.yml` is upstream's test suite, on pushes and PRs to `main` only (`main.yml:4-7`).
- **Upstream tags** can be read without a token: `git ls-remote --tags https://github.com/gristlabs/grist-core`.
- **The org setting** "Allow GitHub Actions to create and approve pull requests" is off and grayed out in the repository. This plan does not need it.

## Design

### Branches and versions

- **`privacyfence` is the default branch.** It holds upstream's latest release tag, plus our files and recorded patches. Releases are cut only from it. Its ruleset requires a pull request and the passing check `image-and-lockout` (`mb1`).
- **`main` stays an untouched mirror of upstream `main`.** It is updated with "Sync fork", and nothing uses it.
- **`pf/UPSTREAM`** holds the upstream tag `privacyfence` is based on, one line (`v1.7.22`).
- **Release tags are `vX.Y.Z-pf.N`.** `X.Y.Z` must equal `package.json`'s `version`, and `N` counts our releases on it, starting at 1. A tag ruleset lets only admins create `v*-pf.*` tags (`mb1`).
- **Image tags** are `X.Y.Z-pf.N` and `latest`.
- **Release notes.** `pf/CHANGELOG.md` gets a `## [X.Y.Z-pf.N] - YYYY-MM-DD` section in a PR before the tag. That section's body becomes the release notes, after the line `Built from gristlabs/grist-core vX.Y.Z.`.

### The image: open source only, pinned, no switch to the full edition

Both `pf-ci.yml` and `pf-release.yml` build the unchanged `Dockerfile`. They set these workflow-level `env`s, holding the `sha256:…` digests (multi-arch index digests) that p3 records:

- `GVISOR_DIGEST`
- `NODE_DIGEST` (for `node:22-trixie`)
- `NODE_SLIM_DIGEST` (for `node:22-trixie-slim`)
- `PYTHON_DIGEST` (for `python:3.11-slim-trixie`)
- `MOCK_OIDC_IMAGE`, for the mock identity provider: `ghcr.io/navikt/mock-oauth2-server@sha256:…`

The build step:

```yaml
build-args: |
  GRIST_BUILD_CHANNEL=core
  GRIST_BUILD_COMMIT=${{ github.sha }}
  GRIST_ALLOW_AUTOMATIC_VERSION_CHECKING=false
  GRIST_EXT_FULL_EDITION_BASE_URL=
build-contexts: |
  ext=ext
  docker.io/gristlabs/gvisor-unprivileged:buster=docker-image://docker.io/gristlabs/gvisor-unprivileged@${{ env.GVISOR_DIGEST }}
  node:22-trixie=docker-image://node@${{ env.NODE_DIGEST }}
  node:22-trixie-slim=docker-image://node@${{ env.NODE_SLIM_DIGEST }}
  python:3.11-slim-trixie=docker-image://python@${{ env.PYTHON_DIGEST }}
```

- **No extensions.** A step before the build runs `mkdir ext && touch ext/dummy`.
- **Two independent guards.** Channel `core` means the switch is never offered, and an empty base URL makes the download impossible. The lock-out check verifies both in the built image.
- **The build-context overrides** replace the `FROM` lines without editing the Dockerfile. buildx and BuildKit match the familiar and the `docker.io/` forms alike.
- **Backup copies.** At each release, `pf-release.yml` copies the gvisor digest to `ghcr.io/privacyfence/gvisor-unprivileged:buster`. If the upstream image disappears, `pf/README.md` says to point the override at that copy, which must be public.
- **Rejected: running upstream's `docker.yml` for `grist-oss`.** It needs Docker Hub secrets, builds the closed image in the same matrix, and would conflict with every upstream change to that file.
- **Rejected: editing the `Dockerfile`.** Build arguments and build contexts reach every setting we need.

### The lock-out check (`pf/e2e/`)

**`pf/e2e/run_lockout.sh <image>`** is bash with `set -euo pipefail`; `set -x` is forbidden anywhere in it. Both workflows call it on an `ubuntu-24.04` runner. In order:

1. **Image report.** The script fails, naming the failing item, unless all of these hold:
   - `docker image inspect <image>` shows `Env` containing `GRIST_EXT_FULL_EDITION_BASE_URL=` and `GRIST_ALLOW_AUTOMATIC_VERSION_CHECKING=false`;
   - `docker run --rm --entrypoint sh <image> -c '…'` succeeds with the commands `test ! -e /grist/ext/app`, `test ! -e /grist/ext/assets`, `test ! -e /grist/_build/ext` and `grep -q "channel = \"core\"" /grist/_build/app/common/version.js` joined by `&&`.

   If the grep does not match because the compiled form differs (for example `channel: "core"`), the worker reads the file in the CI log and adjusts the pattern to whatever form shows the literal `core`. It never removes the check.
2. **The mock identity provider.**
   `docker run -d --name mock-oidc --network host -e SERVER_PORT=8080 -e JSON_CONFIG="$(cat pf/e2e/mock-oidc.json)" "$MOCK_OIDC_IMAGE"`.
3. **Grist.** `docker run -d --name grist --network host <image>` with these environment variables:

   | Variable | Value |
   |---|---|
   | `APP_HOME_URL` | `http://localhost:8484` |
   | `GRIST_SINGLE_ORG` | `team` |
   | `GRIST_ADMIN_EMAIL` | `admin@example.com` |
   | `GRIST_IN_SERVICE` | `true` |
   | `GRIST_FORCE_LOGIN` | `true` |
   | `GRIST_BOOT_KEY` | `$PF_BOOT_KEY` |
   | `GRIST_SESSION_SECRET` | `$(openssl rand -hex 16)` |
   | `GRIST_OIDC_IDP_ISSUER` | `http://localhost:8080/default` |
   | `GRIST_OIDC_IDP_CLIENT_ID` | `grist` |
   | `GRIST_OIDC_IDP_CLIENT_SECRET` | `secret` |
   | `GRIST_OIDC_IDP_SKIP_END_SESSION_ENDPOINT` | `true` |

   `PF_BOOT_KEY` is `$(openssl rand -hex 16)`, masked with `echo "::add-mask::$PF_BOOT_KEY"` and exported.
4. **Wait.** Poll `http://localhost:8484/status` for up to 180 s.
5. **Run the checks.**
   `PF_BOOT_KEY="$PF_BOOT_KEY" python3 pf/e2e/lockout_check.py --grist http://localhost:8484 --site team --email lockout@example.com`.
   The boot key travels in the environment, never on the command line.
6. **The logs.** Fail if `docker logs grist` contains `full edition` (case-insensitive). On any failure, print both containers' logs. A `trap` always removes both containers.

**`pf/e2e/mock-oidc.json`:**

```json
{
  "interactiveLogin": false,
  "tokenCallbacks": [
    {
      "issuerId": "default",
      "tokenExpiry": 300,
      "requestMappings": [
        {
          "requestParam": "grant_type",
          "match": "authorization_code",
          "claims": {
            "sub": "lockout-user",
            "email": "lockout@example.com",
            "email_verified": true,
            "name": "Lock Out"
          }
        }
      ]
    }
  ]
}
```

The mapping matches the token request's `grant_type`. The token exchange sends `grant_type`, `code`, `redirect_uri` and `code_verifier`, not `scope`.

**`pf/e2e/lockout_check.py`** uses Python 3 and the standard library only.

- **Structure.**
  - `class CheckFailed(Exception)`.
  - `@dataclass class Context`, with fields `opener`, `base`, `boot_key`, `site`, `email`, `api_key: str = ""` and `scratch: dict`.
  - `request(ctx, method, path, *, headers=None, json_body=None, raise_for_status=True) -> tuple[int, bytes]`. It sends `Content-Type: application/json` with every JSON body, and catches `urllib.error.HTTPError` to return its status.
  - `main()` reads `PF_BOOT_KEY` from the environment (a missing value gives `CheckFailed("PF_BOOT_KEY is not set")`). It runs the checks in this order, prints `ok: <name>` or `FAIL: <name>: <message>`, and exits 1 at the first failure. Nothing it prints contains a key, a cookie or the boot key.
- **The checks, in order.**
  1. **`check_boot_key_access`.** `GET /api/orgs/<site>/access` with `x-boot-key` answers 200 with a JSON object holding a `users` list.
  2. **`check_free_plan_limits`.**
     - `GET /api/orgs/<site>` with `x-boot-key` answers 200.
     - Read `billingAccount.product.name` and `billingAccount.product.features` from the JSON. A missing path raises `CheckFailed("org JSON has no billingAccount.product")`.
     - The name must be `Free`.
     - The features must have none of the keys `maxUsersPerOrg`, `maxApiCallsPerOrgMonth`, `baseMaxRowsPerDocument`.
  3. **`check_team_membership`.**
     - `PATCH /api/orgs/<site>/access` with `x-boot-key` and `{"delta": {"users": {"newcomer@example.com": "editors", "<email>": "editors"}}}` answers 200.
     - A second `GET …/access` lists both with `access == "editors"`.

     Adding the test user first means the sign-in's final redirect to `/` lands on a site they may open.
  4. **`check_oidc_sign_in`.**
     - An opener with `HTTPCookieProcessor` opens `<base>/login?next=/`. It follows redirects through the mock's `/default/authorize`, back to `/oauth2/callback`.
     - An `HTTPError` on the final hop is caught and ignored; only the next step decides.
     - Then `GET /api/profile/user` answers 200, with `email == <email>`.
     - If the cookie jar holds no cookie from `localhost` after the callback, it raises `CheckFailed("no session cookie: check for a Domain=localhost cookie")`.
  5. **`check_api_key`.**
     - `POST /api/profile/apikey` with the session cookies, `X-Requested-With: XMLHttpRequest` and the JSON body `{"force": true}` answers 200.
     - The body, read as plain text and stripped, is 40 hex characters. It is stored in `ctx.api_key`.
  6. **`check_api_key_use`.** With `Authorization: Bearer <api_key>`:
     - `POST /api/orgs/<site>/workspaces` with `{"name": "lockout"}` answers 200 with the workspace id (an integer).
     - `POST /api/workspaces/<id>/docs` with `{"name": "lockout"}` answers 200 with the doc id (a string).
     - `GET /api/docs/<docId>/tables` answers 200.
- **Rejected: Grist's own browser test suite.** It tests features, not lock-out, and upstream runs it on every release. `pf/README.md` states plainly that our patches are not run through it (see "Fork documentation").

### CI (`.github/workflows/pf-ci.yml`)

- **Triggers:**
  - push to `feature/**`, `fix/**`, `chore/**` and `sync/**`;
  - `pull_request` to `privacyfence`;
  - `workflow_dispatch`.
- **Permissions:** `contents: read`.
- **Pinning.** Every action is pinned by full commit SHA with a version comment. The SHAs are looked up with `git ls-remote https://github.com/<owner>/<action> 'refs/tags/<version>*'`, taking the peeled `^{}` SHA.

There are two jobs.

**`digests`** (always runs) prints, for each of the five external images, `docker buildx imagetools inspect <name:tag> --format '{{.Manifest.Digest}}'`:

- `docker.io/gristlabs/gvisor-unprivileged:buster`
- `node:22-trixie`
- `node:22-trixie-slim`
- `python:3.11-slim-trixie`
- `ghcr.io/navikt/mock-oauth2-server:<MOCK_OIDC_TAG>`

`MOCK_OIDC_TAG` is a workflow env. It is the newest release tag of `navikt/mock-oauth2-server`, from `git ls-remote --tags https://github.com/navikt/mock-oauth2-server`. The job also fails if any digest it prints differs from the matching pinned env. That shows a stale pin in the log; updating a pin is a deliberate PR.

**`image-and-lockout`** runs on `ubuntu-24.04`, with these steps:

1. Check out the repository.
2. Free disk space (copy upstream's "Free some space" step from `docker.yml`).
3. Create the dummy `ext/`.
4. Set up `docker/setup-buildx-action`.
5. Build `linux/amd64` with `docker/build-push-action`: the settings above, `load: true`, `tags: pf-grist:ci`, and `cache-from`/`cache-to` `type=gha,scope=pf-ci`.
6. `bash pf/e2e/run_lockout.sh pf-grist:ci`, with `MOCK_OIDC_IMAGE` in its environment.

### Release (`.github/workflows/pf-release.yml`)

- **Triggers:**
  - push of tags matching `v*-pf.*` (the real release);
  - `pull_request` to `privacyfence` with `paths: [.github/workflows/pf-release.yml, pf/e2e/**, Dockerfile]` (a dry run);
  - `workflow_dispatch` (a dry run).
- **When it publishes.** Only a tag push publishes:
  `env: PUBLISH: ${{ github.event_name == 'push' && github.ref_type == 'tag' }}`.
  The tag name reaches scripts only through `env: TAG: ${{ github.ref_name }}`, never inside `run:` text.
- **Defaults.** Permissions are `contents: read` at workflow level and widened per job. The concurrency group is `pf-release`. No `type=gha` cache is used.

**Jobs:**

1. **`check`** (`contents: read`). It checks out with `fetch-depth: 0` and runs `git fetch origin privacyfence`. When `PUBLISH`:
   - `TAG` must match `^v[0-9]+\.[0-9]+\.[0-9]+-pf\.[0-9]+$`;
   - its `X.Y.Z` must equal `package.json`'s `version`;
   - `git merge-base --is-ancestor "$GITHUB_SHA" origin/privacyfence` must succeed;
   - `pf/CHANGELOG.md` must have a `## [X.Y.Z-pf.N]` section.

   Otherwise it prints `dry run`. Its outputs are `version` (`X.Y.Z-pf.N`, or `X.Y.Z-pf.0` on a dry run) and `publish`.
2. **`build`** (`contents: read`, `packages: write`). A matrix: `amd64` on `ubuntu-24.04` (`linux/amd64`), and `arm64` on `ubuntu-24.04-arm` (`linux/arm64`).
   - When `publish`, it logs in to GHCR with `docker/login-action` and `GITHUB_TOKEN`, then builds with `outputs: type=image,name=ghcr.io/privacyfence/grist-core,push-by-digest=true,name-canonical=true,push=true`, and uploads the digest as an artifact, as upstream's `docker.yml` does.
   - On a dry run it builds with `load: true` instead (amd64), or with `push=false` (arm64).
   - On a dry run, the amd64 job also runs `run_lockout.sh` on the loaded image.
3. **`verify`** (`contents: read`, `packages: read`; only when `publish`). It pulls `ghcr.io/privacyfence/grist-core@<amd64 digest>` and runs `run_lockout.sh` on exactly that digest. So the image that is checked is the image that is published, and the third-party mock never runs in a job holding write tokens.
4. **`publish`** (`contents: write`, `packages: write`, `id-token: write`, `attestations: write`; only when `publish`, after `verify`). It:
   - logs in to GHCR;
   - runs `docker buildx imagetools create` with tags `X.Y.Z-pf.N` and `latest` over both digests;
   - runs `actions/attest-build-provenance` with `subject-name: ghcr.io/privacyfence/grist-core`, the manifest digest, and `push-to-registry: true`;
   - copies the gvisor digest to `ghcr.io/privacyfence/gvisor-unprivileged:buster`;
   - creates the GitHub release `vX.Y.Z-pf.N`, with the notes described above.

No `docker/metadata-action`: the tags are computed in `check`.

### Upstream sync (`.github/workflows/pf-sync.yml`)

- **Triggers:** `schedule` (`cron: '23 6 * * 1'`) and `workflow_dispatch`.
- **Permissions:** `contents: read`. All writes use the repository secret `PF_SYNC_TOKEN` (`mb1`), a fine-grained token limited to this repository, with Contents, Pull requests, Issues and Workflows set to read and write.
  - `GITHUB_TOKEN` cannot push the upstream workflow changes a merge brings, and a PR opened with it would trigger no checks.
  - With `PF_SYNC_TOKEN`, the PR runs `pf-ci.yml` by itself.

It has one job, which runs these steps:

1. **Find the latest upstream release.**
   `latest=$(git ls-remote --tags https://github.com/gristlabs/grist-core | sed -n 's#.*refs/tags/\(v[0-9]*\.[0-9]*\.[0-9]*\)$#\1#p' | sort -V | tail -1)`.
   Stop successfully in any of these cases:
   - it equals the content of `pf/UPSTREAM`;
   - `sync/$latest` exists on origin;
   - an open issue titled `Upstream $latest needs a manual merge` exists (`gh issue list --state open --search "in:title \"Upstream $latest needs a manual merge\""`).
2. **Merge it.**
   - Check out `privacyfence` with `fetch-depth: 0` and `token: ${{ secrets.PF_SYNC_TOKEN }}`.
   - Fetch the tag: `git fetch https://github.com/gristlabs/grist-core "refs/tags/$latest:refs/tags/$latest"`.
   - Create branch `sync/$latest`, and run `git merge --no-ff -m "Merge upstream $latest" "$latest"` as `github-actions[bot]`.
3. **On a conflict.** Record the conflicting files with `git diff --name-only --diff-filter=U`, then run `git merge --abort`. Open the issue `Upstream $latest needs a manual merge`, listing those files, then stop successfully.
4. **Record and push.** Write `$latest` to `pf/UPSTREAM`, commit `Base on upstream $latest`, and push the branch.
5. **Open the PR.**
   `gh pr create --base privacyfence --head "sync/$latest" --title "Merge upstream $latest"`. The body contains:
   - a link to upstream's release page;
   - the list of `.github/workflows/*` files the merge added or changed (`git diff --name-status privacyfence...HEAD -- .github/workflows`), with the line: "Disable any new upstream workflow in the Actions tab before merging, unless it is pf-*.yml.";
   - a reminder to check `pf/PATCHES.md`.

### Fork documentation and policy (`pf/README.md`, `pf/PATCHES.md`)

**`pf/README.md`** covers:

- what the fork is and why;
- the image name and tags;
- the branches and the rulesets;
- the release steps:
  1. a changelog PR;
  2. the maintainer pushes the tag;
  3. the first time, make the `grist-core` and `gvisor-unprivileged` packages public;
  4. check the release with `gh attestation verify`;
- the sync:
  - what `pf-sync.yml` does and how to review its PR;
  - new upstream workflows;
  - `PF_SYNC_TOKEN`'s expiry, and renewing it;
  - that GitHub disables scheduled workflows in a repository with no activity for 60 days, and how to re-enable it in the Actions tab;
- the lock-out check: what each check proves, and what a failure means;
- the pins: `digests` shows drift, and updating a pin is a PR;
- the gvisor fallback;
- that our patches are not run through upstream's test suite, which runs only on `main`. A patched release should be smoke-tested by hand in the suite.
- the licence: built from grist-core under Apache-2.0, not an official Grist release, and keeping upstream's `LICENSE.txt` and `NOTICE.txt`.

**`pf/PATCHES.md`** has two tables:

- **Patches:** commit on `privacyfence`, upstream file, why, upstream issue or PR, and when it can be dropped.
- **Declined upstream changes:** upstream release, what it gates or removes, and what was done.

It also states this rule:

- **A gating change.** A sync PR whose lock-out check fails is never merged as is. If the cause is one gating change, a revert commit of exactly that change goes on the sync branch, and is recorded.
- **A removal.** If upstream *removes* a feature the check needs (for example OIDC), the fork stays on its last good release. An issue records it, and whether to carry a re-add patch is the maintainer's decision.

### Rejected

- **Tracking upstream `main` instead of release tags.** It changes daily, and it is not what Grist Labs releases.
- **Rebasing our commits on each upstream release.** It rewrites `privacyfence`'s history and breaks tags and digests. Our additions are separate files, so merges stay conflict-free.
- **Deleting upstream workflow files.** That conflicts with every upstream change to them; they are disabled in the Actions tab instead.
- **The org-wide "Allow GitHub Actions to create and approve pull requests" setting.** `PF_SYNC_TOKEN` opens the PRs, and its PRs trigger checks, which `GITHUB_TOKEN`'s would not.

## Manual steps

The steps are in the [step-by-step page](https://claude.ai/artifact/KhQXY5KJJJip5XK9MiqVQf), whose source is `pf/docs/operational-fork-plan-manual-steps.html`.

- **Before:** `mb1-branch-actions-and-protection`:
  1. Create `privacyfence` from `a10b722` and make it the default branch.
  2. Disable the nine upstream workflows.
  3. Add the branch ruleset and the tag ruleset.
  4. Create `PF_SYNC_TOKEN`.
- **After:** `ma1-review-ci` (before the PR merges): read the pf-ci and pf-release dry-run logs on the PR.
- **After merging,** not part of `/implement` (the page's last section, and `pf/README.md`): the first release, `v1.7.22-pf.1`, which the suite plan's `mb2` needs.

## Risks and open questions

- **The mock identity provider behaves differently** from its README (config keys, or a userinfo without `email_verified`). `check_oidc_sign_in` fails, with the mock's log. The worker stops with `status=blocked` and reports the log, rather than switching providers.
- **The org JSON has no `billingAccount.product`.** `check_free_plan_limits` fails with that message. The worker reads `app/gen-server/ApiServer.ts` (`GET /api/orgs/:oid`) and adjusts only the JSON path; it never removes the check. If the plan information is not exposed at all, it stops with `status=blocked`.
- **`ubuntu-24.04-arm`** may not be available to the organization. The arm64 job of the PR dry run fails. The worker stops with `status=blocked`; it never drops arm64.
- **`pf-sync.yml` and the tag path of `pf-release.yml`** can only run after the merge. The PR runs the release dry run; the sync is first exercised by the first upstream release after merging.
- **Upstream removes OIDC.** There is no code change for it; it is the policy above.

## Implementation manifest

```yaml
plan_slug: operational-fork
feature_branch: feature/operational-fork
max_parallel: 2
manual_steps_artifact: https://claude.ai/artifact/KhQXY5KJJJip5XK9MiqVQf
manual_steps_source: pf/docs/operational-fork-plan-manual-steps.html
manual_before:
  - id: mb1-branch-actions-and-protection
    title: Create the privacyfence branch from v1.7.22 as the default, disable the upstream workflows, add the branch and tag rulesets, and create PF_SYNC_TOKEN
    why: /implement opens its PR to privacyfence; upstream workflows would otherwise run Docker Hub pushes, Fly deploys and the CLA bot; without the branch ruleset the lock-out check gates nothing; without the tag ruleset anyone with write access could release; pf-sync.yml needs PF_SYNC_TOKEN to push workflow changes and open PRs that run checks
    done_when: privacyfence is the default branch at a10b722; the Actions page shows docker.yml, docker_latest.yml, the four fly-*.yml, cla.yml, self-hosted.yml and translation_keys.yml as disabled; Settings → Rules lists a branch ruleset on privacyfence requiring a pull request and the status check image-and-lockout, and a tag ruleset on v*-pf.* restricting creation to admins; Settings → Secrets and variables → Actions lists PF_SYNC_TOKEN
manual_after:
  - id: ma1-review-ci
    title: Read the pf-ci and pf-release dry-run runs on the PR
    why: The runs are green by acceptance; a person confirms that the image report, the six "ok:" lines and both architectures are what the plan promises, before the fork starts publishing
verify_after_merge:
  - python3 -m pip install -q -r pf/requirements-dev.txt && python3 -m pytest pf/tests -q && ruff check pf && sh -c 'set -- .github/workflows/pf-*.yml; [ -e "$1" ] || exit 0; actionlint "$@"'
final_checks:
  - pf/docs/operational-fork-plan.md and pf/docs/operational-fork-plan-manual-steps.html are deleted and nothing links to them
  - pf/CHANGELOG.md has entries under "## [Unreleased]" and no version heading
  - git diff --stat a10b7227365adfe2555be40ae87bb9741284c0ca..HEAD touches only .claude/, pf/ and .github/workflows/pf-*.yml
  - the pf-ci.yml and pf-release.yml runs on the PR's head are green
phases:
  - id: p1-basics
    title: Fork documentation skeleton, policy files and Python tooling
    depends_on: []
    complexity: S
    touches:
      - pf/README.md
      - pf/PATCHES.md
      - pf/UPSTREAM
      - pf/requirements-dev.txt
      - pf/ruff.toml
      - pf/tests/__init__.py
      - pf/tests/test_repo_files.py
      - .claude/toolkit.yaml
    brief: |
      Read pf/docs/operational-fork-plan.md: "Branches and versions" and "Fork documentation and policy".
      1. pf/UPSTREAM with the single line v1.7.22.
      2. pf/requirements-dev.txt: pytest==8.4.2, ruff==0.14.1 and actionlint-py==1.7.8.1. pf/ruff.toml: line-length = 120, target-version = "py312".
      3. pf/PATCHES.md with the two empty tables and the rule, exactly as the Design describes.
      4. pf/README.md with every section listed in the Design. The release, sync, lock-out and pins sections may say "completed by a later phase of this plan"; p6 completes them.
      5. .claude/toolkit.yaml:
         - add pf/README.md to docs.must_read after README.md;
         - add `sh -c 'set -- .github/workflows/pf-*.yml; [ -e "$1" ] || exit 0; actionlint "$@"'` to verify.fast and verify.dod (it passes while no pf-*.yml exists yet);
         - add a pf-release.yml note: "Its pull_request dry run runs by itself on PRs that touch it".
      6. pf/tests/test_repo_files.py: test_upstream_file_is_a_release_tag (pf/UPSTREAM matches ^v\d+\.\d+\.\d+\n?$) and test_upstream_matches_package_version (equals "v" + package.json's version).
      7. Run `python3 -m pip install -q -r pf/requirements-dev.txt`, `python3 -m pytest pf/tests -q` and `ruff check pf`.
    acceptance:
      - python3 -m pytest pf/tests -q passes
      - ruff check pf passes
      - grep -n "pf/README.md" .claude/toolkit.yaml finds it

  - id: p2-lockout-check
    title: The lock-out check script, the mock identity provider config and the runner script
    depends_on: [p1-basics]
    complexity: M
    touches:
      - pf/e2e/lockout_check.py
      - pf/e2e/mock-oidc.json
      - pf/e2e/run_lockout.sh
      - pf/tests/test_lockout_check.py
    brief: |
      Read pf/docs/operational-fork-plan.md, section "The lock-out check".
      1. pf/e2e/mock-oidc.json verbatim.
      2. pf/e2e/lockout_check.py with the structure, the six checks in order, and the output exactly as designed. Never print the boot key, the API key or a cookie.
      3. pf/e2e/run_lockout.sh with the six steps exactly as designed: the trap cleanup, masking, the boot key passed only in the environment, and no `set -x`. Make it executable with `git update-index --chmod=+x`.
      4. pf/tests/test_lockout_check.py, with a fake opener returning canned responses per (method, path). Required tests:
         - test_boot_key_access_ok, test_boot_key_access_no_users_list_fails;
         - test_free_plan_ok, test_free_plan_limit_key_fails, test_free_plan_missing_product_fails;
         - test_team_membership_ok, test_team_membership_role_missing_fails;
         - test_sign_in_ok_even_if_final_hop_403, test_sign_in_wrong_email_fails;
         - test_api_key_plain_text_ok, test_api_key_refused_fails;
         - test_api_key_use_ok, test_api_key_use_workspace_refused_fails;
         - test_json_body_sends_content_type;
         - test_missing_boot_key_env_fails;
         - test_main_stops_at_first_failure_and_exits_1;
         - test_secrets_never_printed (capsys: neither the boot key nor the API key appears).
      5. Run `python3 -m pytest pf/tests -q`, `ruff check pf` and `bash -n pf/e2e/run_lockout.sh`, and check that `grep -n "set -x" pf/e2e/run_lockout.sh` finds nothing.
    acceptance:
      - python3 -m pytest pf/tests -q passes, including every named test
      - bash -n pf/e2e/run_lockout.sh exits 0, and grep -c "set -x" pf/e2e/run_lockout.sh prints 0
      - grep -n "def check_free_plan_limits" pf/e2e/lockout_check.py finds it

  - id: p3-ci
    title: pf-ci.yml builds the pinned open-source image and runs the lock-out check
    depends_on: [p2-lockout-check]
    complexity: M
    touches:
      - .github/workflows/pf-ci.yml
      - pf/e2e/**
      - pf/tests/test_lockout_check.py
    brief: |
      Read pf/docs/operational-fork-plan.md: "The image", "The lock-out check", "CI" and "Risks".
      1. Look up the action SHAs with `git ls-remote https://github.com/<owner>/<repo> 'refs/tags/<version>*'`, using the peeled ^{} SHA:
         - actions/checkout v4
         - docker/setup-buildx-action v3
         - docker/build-push-action v6

         Look up MOCK_OIDC_TAG as the newest vX.Y.Z tag of navikt/mock-oauth2-server, the same way; the image tag has no leading v.
      2. Write .github/workflows/pf-ci.yml with both jobs. First push it with the five digest envs set to the placeholder `sha256:0`. The digests job prints the real digests and fails on the mismatch; that is expected. Read the run, put the five printed digests into the envs, and push again.
      3. Read the image-and-lockout run. If it fails, fix pf/e2e/* or pf/tests/test_lockout_check.py only. Allowed fixes:
         - the version.js grep pattern (see "The lock-out check", step 1);
         - a JSON path or header the Risks name.

         Each of these is a stop with status=blocked, reporting the log:
         - check_oidc_sign_in fails because of the mock provider;
         - a check shows an API refused (403 or 404) rather than a format difference;
         - a "full edition" log line appears.
      4. Run `actionlint .github/workflows/pf-ci.yml` and `python3 -m pytest pf/tests -q`.
    acceptance:
      - the pf-ci.yml run on the pushed branch is green, with all six "ok:" lines and the image report in the log
      - actionlint .github/workflows/pf-ci.yml passes
      - grep -c "docker-image://" .github/workflows/pf-ci.yml prints 4
      - grep -n "GRIST_BUILD_CHANNEL=core" .github/workflows/pf-ci.yml finds it

  - id: p4-release
    title: pf-release.yml with a pull-request dry run, a verified tag release to GHCR and provenance
    depends_on: [p3-ci]
    complexity: M
    touches:
      - .github/workflows/pf-release.yml
    brief: |
      Read pf/docs/operational-fork-plan.md: "Branches and versions", "The image" and "Release".
      1. Write .github/workflows/pf-release.yml with the triggers, the PUBLISH and TAG envs, and the jobs check, build, verify and publish exactly as designed, with per-job permissions.
         - Copy the by-digest build, digest artifact and manifest-list pattern from upstream's .github/workflows/docker.yml (build_and_push and publish jobs), with ghcr.io/privacyfence/grist-core as the only image.
         - Use the same digest envs and action SHAs as pf-ci.yml. Add actions/upload-artifact v4, actions/download-artifact v4, docker/login-action v3 and actions/attest-build-provenance v2, with SHAs looked up the same way.
      2. Run `actionlint .github/workflows/pf-release.yml`.
      3. Open nothing. Push the phase branch; the pull_request trigger runs only once the feature PR exists. So in this phase, also run the dry run once: temporarily add `push: branches: ['feature/**']` to the triggers, push, and read the run (check and build on both architectures, plus the lock-out check on amd64). Then remove that temporary trigger and push again.
         - Stop condition: the arm64 job fails because no runner picks it up (see Risks). Stop with status=blocked.
    acceptance:
      - actionlint .github/workflows/pf-release.yml passes
      - the temporary dry run on the phase branch was green on both architectures, including the lock-out check (link the run in the phase report)
      - grep -n "github.ref_type == 'tag'" .github/workflows/pf-release.yml finds the publish condition
      - grep -n "merge-base --is-ancestor" .github/workflows/pf-release.yml finds the branch check
      - grep -c "branches: \['feature/\*\*'\]" .github/workflows/pf-release.yml prints 0

  - id: p5-sync
    title: pf-sync.yml opens a pull request for each new upstream release
    depends_on: [p3-ci]
    complexity: S
    touches:
      - .github/workflows/pf-sync.yml
    brief: |
      Read pf/docs/operational-fork-plan.md, section "Upstream sync".
      1. Write .github/workflows/pf-sync.yml with the five steps exactly as designed:
         - every write (checkout token, push, gh) uses secrets.PF_SYNC_TOKEN, with GH_TOKEN set to it for gh;
         - workflow-level permissions are contents: read;
         - actions/checkout is pinned by SHA as in pf-ci.yml.
      2. Run `actionlint .github/workflows/pf-sync.yml`.
      3. Check step 1's pipeline locally: `printf 'x\trefs/tags/v1.7.9\nx\trefs/tags/v1.7.22\nx\trefs/tags/v1.7.22^{}\nx\trefs/tags/v2.0.0-rc1\n' | sed -n 's#.*refs/tags/\(v[0-9]*\.[0-9]*\.[0-9]*\)$#\1#p' | sort -V | tail -1` must print v1.7.22.
         - Stop condition: if it prints anything else, stop with status=blocked.
    acceptance:
      - actionlint .github/workflows/pf-sync.yml passes
      - grep -n "PF_SYNC_TOKEN" .github/workflows/pf-sync.yml finds it
      - grep -n "needs a manual merge" .github/workflows/pf-sync.yml finds both the issue search and the issue creation

  - id: p6-docs-retire
    title: Complete the fork's README and changelog, delete the plan
    depends_on: [p4-release, p5-sync]
    complexity: S
    touches:
      - pf/README.md
      - pf/CHANGELOG.md
      - pf/docs/operational-fork-plan.md
      - pf/docs/operational-fork-plan-manual-steps.html
    brief: |
      1. pf/README.md: complete every section the Design lists. Concretely:
         - the release steps with exact commands;
         - the sync review checklist, including new upstream workflows;
         - PF_SYNC_TOKEN renewal;
         - the 60-day scheduled-workflow note;
         - the six checks and the image report, and what a failure means;
         - the pins and the digests job;
         - the gvisor fallback, including that the copy must be public;
         - the upstream-tests gap;
         - the licence statement.
      2. pf/CHANGELOG.md, "## [Unreleased]", "### Added":
         - "- **Open-source image.** `ghcr.io/privacyfence/grist-core`, built from grist-core with no full-edition extensions, the full-edition switch off and every base image pinned by digest, for amd64 and arm64, with build provenance."
         - "- **Lock-out check.** Every build signs in through OIDC, creates an API key and uses it, and checks the boot key, the team-site access API and the free plan's limits; a build where any of them is locked fails and cannot be merged or released."
         - "- **Upstream sync.** A weekly workflow opens a pull request for each new upstream release, listing any upstream workflow it brings."
      3. Delete pf/docs/operational-fork-plan.md and pf/docs/operational-fork-plan-manual-steps.html; `grep -rn --exclude-dir=.git "operational-fork-plan" pf .claude .github` finds nothing.
    acceptance:
      - test ! -e pf/docs/operational-fork-plan.md
      - grep -rn --exclude-dir=.git "operational-fork-plan" pf .claude .github finds nothing
      - grep -n "Lock-out check" pf/CHANGELOG.md finds the entry
```
