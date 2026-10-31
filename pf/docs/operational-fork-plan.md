# An operational PrivacyFence fork of grist-core

## Goal

`privacyfence/grist-core` builds and releases its own Grist image, `ghcr.io/privacyfence/grist-core`. The `privacyfence-suite` stack and grist-provisioner then never depend on a Grist build that can lock a feature behind a paid edition. That covers the OIDC sign-in the suite uses, the boot key, the team-site access API and API keys.

The fork must:

1. **Build only the open-source code.** No full-edition extensions, and no runtime download of them.
2. **Change upstream as little as possible.** Our own files live under `pf/`, `.claude/` and `.github/workflows/pf-*.yml`; upstream files change only as recorded patches.
3. **Prove at every build that nothing is locked.** A CI check signs in through OIDC and uses the APIs the suite needs. An upstream change that gates them fails the build before it can be released.
4. **Take upstream releases only through a reviewed pull request,** opened automatically when upstream tags a release.

## Current state

- **The fork.** `privacyfence/grist-core` is a fresh fork. Its `main` is upstream's head (`aa1b8a1`), and it has no tags. Upstream's latest release is `v1.7.22`, commit `a10b7227365adfe2555be40ae87bb9741284c0ca` ("v1.7.22 (#2729)"), which is in the fork's history. This plan's branch is cut from that commit, and adds `.claude/toolkit.yaml` and `pf/CHANGELOG.md`.
- **Two upstream images, one Dockerfile** (`Dockerfile`, unchanged by this plan).
  - **Extensions.** A `FROM scratch AS ext` stage takes extensions from a build context (`--build-context ext=<dir>`). Upstream's `grist` image checks out the closed `grist-ee` extensions there (`.github/workflows/docker.yml`, step "Check out the ext/ directory", `buildtools/checkout-ext-directory.sh grist-ee`). `grist-oss` uses a dummy `ext/` ("Add a dummy ext/ directory").
  - **Build arguments.** `GRIST_BUILD_CHANNEL` and `GRIST_BUILD_COMMIT` go to `yarn run build:prod`. `GRIST_ALLOW_AUTOMATIC_VERSION_CHECKING` (default `false`) and `GRIST_EXT_FULL_EDITION_BASE_URL` (default `https://grist-static.com/grist-full-edition`) become runtime `ENV`s.
  - **The sandbox.** It comes from `FROM docker.io/gristlabs/gvisor-unprivileged:buster AS sandbox`, a prebuilt binary image Grist Labs publishes.
  - **Runtime.** Entrypoint `["./sandbox/docker_entrypoint.sh"]`, command `["./sandbox/run.sh"]`, working directory `/grist`, user `grist` created with `useradd`.
- **How a running Grist can switch itself to the full edition** (`app/server/lib/bootstrapFullEdition.ts`).
  - **When it may.** It downloads the full-edition extensions into `/persist/ext/grist-full-edition` and restarts into them. That happens only when the build's channel is `release` (`defaultIsReleaseBuild`, line 86) and `GRIST_EXT_FULL_EDITION_BASE_URL` is not empty (`getBaseUrl`, lines 96-102: "an explicitly empty value disables the switch").
  - **The channel.** It is set by `buildtools/build.sh` (`build_version_file`, lines 30-45): `GRIST_BUILD_CHANNEL` when given; otherwise `release` for a clean checkout of the tag `v<version>`, and `core` for anything else. Docker builds have no `.git`, because `.dockerignore` lists only the needed files, so the build argument decides.
- **What is gated today.**
  - The Admin panel's authentication section shows OIDC and SAML as needing an activation key (`isMissingRequiredKey`, `app/client/ui/AuthenticationSection.ts:103-105`). That is client-side only.
  - The server builds OIDC from the environment with no edition check (`app/server/lib/coreLogins.ts:44-47`, `getOIDCLoginSystem`).
  - The README lists "Single sign-on (SSO) via OIDC or SAML" under "Features not in grist-core".
- **Upstream workflows** in `.github/workflows`:
  - `docker.yml` and `docker_latest.yml` push to Docker Hub with Grist Labs' secrets.
  - `fly-build.yml`, `fly-deploy.yml`, `fly-cleanup.yml` and `fly-destroy.yml` handle preview deployments.
  - `cla.yml` handles the CLA bot; `self-hosted.yml` writes to a Grist Labs project; `translation_keys.yml` only runs for `gristlabs`.
  - `main.yml` runs upstream's test suite on pushes and PRs to `main`.

  None of them is useful to the fork except `main.yml`, which upstream already runs on every release.
- **Upstream tags** can be read without a token: `git ls-remote --tags https://github.com/gristlabs/grist-core`.

## Design

### Branches and versions

- **`privacyfence`** is the fork's default branch. It is upstream's latest release tag, plus our files, plus any recorded patches. Releases are cut only from it.
- **`main`** stays an untouched mirror of upstream `main`, updated with GitHub's "Sync fork" button, so it never conflicts.
- **`pf/UPSTREAM`** holds the upstream tag that `privacyfence` is based on, one line, for example `v1.7.22`.
- **Release tags** are `vX.Y.Z-pf.N`: `X.Y.Z` is the upstream version (it must equal `package.json`'s `version`), and `N` counts our releases on it, starting at 1. Image tags are `X.Y.Z-pf.N` and `latest`.
- **Release notes.** `pf/CHANGELOG.md` gets a `## [X.Y.Z-pf.N] - YYYY-MM-DD` section in the PR before the tag. Its body becomes the GitHub release notes, preceded by the line `Built from gristlabs/grist-core vX.Y.Z.`.

### The image: open source only, no switch to the full edition

Both `pf-ci.yml` and `pf-release.yml` build the unchanged `Dockerfile` with exactly these settings:

```yaml
build-args: |
  GRIST_BUILD_CHANNEL=core
  GRIST_BUILD_COMMIT=${{ github.sha }}
  GRIST_ALLOW_AUTOMATIC_VERSION_CHECKING=false
  GRIST_EXT_FULL_EDITION_BASE_URL=
build-contexts: |
  ext=ext
  docker.io/gristlabs/gvisor-unprivileged:buster=docker-image://docker.io/gristlabs/gvisor-unprivileged@${{ env.GVISOR_DIGEST }}
```

- **No extensions.** Before the build, a step runs `mkdir ext && touch ext/dummy`, as upstream's `grist-oss` does.
- **Two independent guards against the full edition.** Channel `core` means the switch is never offered, and an empty base URL means no download is possible.
- **The sandbox image is pinned.** `GVISOR_DIGEST` is a workflow-level `env` holding the `sha256:…` digest of `docker.io/gristlabs/gvisor-unprivileged:buster` at the time p3 runs. The build-context override replaces the `FROM` without editing the Dockerfile.
- **A backup copy.** `pf-release.yml` also copies that digest to `ghcr.io/privacyfence/gvisor-unprivileged:buster` at each release. If the upstream image ever disappears, `pf/README.md` says to point the override at the copy.
- **Rejected: building upstream's `grist-oss` image ourselves through their `docker.yml`.** It needs Docker Hub secrets, builds the closed image in the same matrix, and would conflict with every upstream change to that file.
- **Rejected: editing the `Dockerfile`.** Build arguments and build contexts reach every setting we need. A Dockerfile patch would have to be carried through every upstream release.

### The lock-out check (`pf/e2e/`)

**`pf/e2e/run_lockout.sh <image>`** (bash, `set -euo pipefail`) is called by both workflows on an `ubuntu-24.04` runner. It runs these steps:

1. **Image settings.** `docker image inspect <image>` must show `Env` containing exactly `GRIST_EXT_FULL_EDITION_BASE_URL=` and `GRIST_ALLOW_AUTOMATIC_VERSION_CHECKING=false`. `docker run --rm --entrypoint sh <image> -c 'test ! -e /grist/ext/assets && test ! -e /grist/_build/ext'` must succeed.
2. **The mock identity provider.** Start it with `docker run -d --name mock-oidc --network host -e SERVER_PORT=8080 -e JSON_CONFIG="$(cat pf/e2e/mock-oidc.json)" ghcr.io/navikt/mock-oauth2-server:2.1.10`.
3. **Grist.** Start `docker run -d --name grist --network host` with:

   | Variable | Value |
   |---|---|
   | `APP_HOME_URL` | `http://localhost:8484` |
   | `GRIST_SINGLE_ORG` | `team` |
   | `GRIST_ADMIN_EMAIL` | `admin@example.com` |
   | `GRIST_IN_SERVICE` | `true` |
   | `GRIST_FORCE_LOGIN` | `true` |
   | `GRIST_BOOT_KEY` | a random 32-hex value |
   | `GRIST_SESSION_SECRET` | a random 32-hex value |
   | `GRIST_OIDC_IDP_ISSUER` | `http://localhost:8080/default` |
   | `GRIST_OIDC_IDP_CLIENT_ID` | `grist` |
   | `GRIST_OIDC_IDP_CLIENT_SECRET` | `secret` |
   | `GRIST_OIDC_IDP_SKIP_END_SESSION_ENDPOINT` | `true` |

   The two random values are generated with `openssl rand -hex 16` and masked with `::add-mask::`.
4. **Wait.** Poll `http://localhost:8484/status` for up to 180 s.
5. **The checks.** Run `python3 pf/e2e/lockout_check.py --grist http://localhost:8484 --boot-key "$BOOT" --site team --email lockout@example.com`.
6. **Logs.** Fail if `docker logs grist` contains `full edition` (case-insensitive). On any failure, print `docker logs mock-oidc` and `docker logs grist`, then exit 1. Always remove both containers at the end (`trap`).

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
          "requestParam": "scope",
          "match": "*",
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

**`pf/e2e/lockout_check.py`** is Python 3, standard library only (`urllib.request`, `http.cookiejar`, `json`, `argparse`). Each check is a function `check_<name>(ctx) -> None` that raises `CheckFailed(message)`. `main()` runs them in this order, prints `ok: <name>` or `FAIL: <name>: <message>`, and exits 1 at the first failure:

1. **`check_oidc_sign_in`.**
   - An opener with an `HTTPCookieProcessor` opens `<grist>/login?next=/` and follows redirects, through the mock's `/default/authorize`, back to `/oauth2/callback`.
   - Then `GET <grist>/api/profile/user` must answer 200, with `email == <email>`.
2. **`check_api_key`.**
   - `POST <grist>/api/profile/apikey` with the session cookies, the header `X-Requested-With: XMLHttpRequest`, and the JSON body `{"force": true}`, must answer 200 with a 40-character key.
   - `GET <grist>/api/orgs` with `Authorization: Bearer <key>` must then answer 200.
3. **`check_boot_key_access`.** `GET <grist>/api/orgs/<site>/access` with `x-boot-key` must answer 200, with a JSON object holding a `users` list.
4. **`check_team_membership`.**
   - `PATCH <grist>/api/orgs/<site>/access` with `x-boot-key` and the body `{"delta": {"users": {"newcomer@example.com": "editors"}}}` must answer 200.
   - A second `GET …/access` must list `newcomer@example.com` with `access == "editors"`.

The HTTP layer is one function, `request(ctx, method, path, *, headers=None, body=None) -> tuple[int, bytes]`, on a `Context` dataclass that holds the opener, the base URL, the boot key, the site and the email. That way the unit tests can replace `ctx.opener` with a fake.

**Rejected: Grist's own browser test suite (mocha and Selenium).** It is heavy and tests Grist's features, not the lock-out question. Upstream runs it on every release.

### CI (`.github/workflows/pf-ci.yml`)

- **Triggers:** push to `privacyfence`, `feature/**`, `fix/**`, `chore/**` and `sync/**`; `pull_request` to `privacyfence`; and `workflow_dispatch`.
- **Permissions:** `contents: read`.
- **Actions** are pinned by full commit SHA, with a version comment.

It has one job, `image-and-lockout`, on `ubuntu-24.04`:

1. Check out the repository.
2. Free disk space (copy upstream's "Free some space" step).
3. Create the dummy `ext/`.
4. Run `docker/setup-buildx-action`.
5. Build `linux/amd64` with `docker/build-push-action`, using the settings above, with `load: true`, `tags: pf-grist:ci`, and `cache-from`/`cache-to` `type=gha,scope=pf-ci`.
6. Run `bash pf/e2e/run_lockout.sh pf-grist:ci`.
7. Print `docker buildx imagetools inspect docker.io/gristlabs/gvisor-unprivileged@${GVISOR_DIGEST}` (the pinned digest stays resolvable).

### Release (`.github/workflows/pf-release.yml`)

- **Triggers:** push of tags matching `v*-pf.*`, and `workflow_dispatch` with input `dry_run` (boolean, default `true`).
- **Permissions:** `contents: write`, `packages: write`, `id-token: write` and `attestations: write`.
- **Concurrency group:** `pf-release`.

**Jobs:**

1. **`check`.**
   - On a tag: the name must match `^v[0-9]+\.[0-9]+\.[0-9]+-pf\.[0-9]+$`, and its `X.Y.Z` must equal `package.json`'s `version`.
   - The tag commit must be reachable from `origin/privacyfence` (`git merge-base --is-ancestor`).
   - `pf/CHANGELOG.md` must have a `## [X.Y.Z-pf.N]` section.
   - On a dry run, it takes the version from `package.json`, uses `N=0`, and skips the tag and changelog checks.
2. **`build`**, a matrix of `amd64` on `ubuntu-24.04` (`linux/amd64`) and `arm64` on `ubuntu-24.04-arm` (`linux/arm64`).
   - It builds with the same settings.
   - On amd64 only, it builds once with `load: true` and runs `pf/e2e/run_lockout.sh`; the job fails if the check fails.
   - It then builds with `outputs: type=image,name=ghcr.io/privacyfence/grist-core,push-by-digest=true,name-canonical=true,push=<not dry_run>` and uploads the digest as an artifact, as upstream's `docker.yml` does.
3. **`publish`** (skipped on a dry run) does the following:
   - It logs in to GHCR with `GITHUB_TOKEN`.
   - `docker buildx imagetools create` makes the manifest list with tags `X.Y.Z-pf.N` and `latest`.
   - It runs `actions/attest-build-provenance` on the manifest digest (`subject-name: ghcr.io/privacyfence/grist-core`, `push-to-registry: true`).
   - It copies the gvisor digest to `ghcr.io/privacyfence/gvisor-unprivileged:buster`.
   - It creates the GitHub release named `vX.Y.Z-pf.N`, with notes made of the line `Built from gristlabs/grist-core vX.Y.Z.` followed by the changelog section's body.

### Upstream sync (`.github/workflows/pf-sync.yml`)

- **Triggers:** `schedule` (`cron: '23 6 * * 1'`) and `workflow_dispatch`.
- **Permissions:** `contents: write`, `pull-requests: write`, `issues: write` and `actions: write`.

It has one job, which runs these steps:

1. **Find the newest upstream release.** `latest=$(git ls-remote --tags https://github.com/gristlabs/grist-core | sed -n 's#.*refs/tags/\(v[0-9]*\.[0-9]*\.[0-9]*\)$#\1#p' | sort -V | tail -1)`. If it equals `pf/UPSTREAM`, or a branch `sync/$latest` already exists on origin, stop.
2. **Merge it.** Check out `privacyfence` with `fetch-depth: 0`, then run `git fetch https://github.com/gristlabs/grist-core "refs/tags/$latest:refs/tags/$latest"`. Create branch `sync/$latest` and run `git merge --no-ff -m "Merge upstream $latest" "$latest"`, with `git config user.name "github-actions[bot]"` and the matching noreply email.
3. **On a conflict:** `git merge --abort`. Open an issue titled `Upstream $latest needs a manual merge`, listing the conflicting files from `git diff --name-only --diff-filter=U` (captured before the abort), with `gh issue create`. Then stop, successfully.
4. **Record and push.** Write `$latest` to `pf/UPSTREAM`, commit `Base on upstream $latest`, and push the branch.
5. **Open the PR:** `gh pr create --base privacyfence --head "sync/$latest" --title "Merge upstream $latest"`. Its body links upstream's release page and reminds the reviewer to check `pf/PATCHES.md`.
6. **Run CI on it:** `gh workflow run pf-ci.yml --ref "sync/$latest"`. Pull requests opened by `GITHUB_TOKEN` do not trigger workflows, but a dispatch does.

### Fork documentation and policy (`pf/README.md`, `pf/PATCHES.md`)

**`pf/README.md`** covers:

- what the fork is and why;
- the image name and tags;
- the branches and how to update `main` ("Sync fork");
- the release steps: a changelog PR, the maintainer pushes the tag, then make the package public the first time;
- what `pf-sync.yml` does and how to review its PR;
- the lock-out check: what it proves, and what to do when it fails;
- the gvisor fallback;
- that the image is built from grist-core under Apache-2.0, is not an official Grist release, and keeps upstream's `LICENSE.txt` and `NOTICE.txt`.

**`pf/PATCHES.md`** records two things:

- **Patches**, as a table: commit on `privacyfence`, upstream file, why, upstream issue or PR, and when it can be dropped.
- **Declined upstream changes**, as a table: upstream commit or release, what it gates, and how it was reverted. It starts empty, with this rule: a sync PR whose lock-out check fails is never merged as is. The fix is a revert commit of exactly the gating change on the sync branch, recorded here.

### Rejected

- **Tracking upstream `main` instead of release tags.** Upstream `main` changes daily and is not what Grist Labs releases.
- **Rebasing our commits on each upstream release.** It rewrites `privacyfence`'s history and breaks tags and digests. Merging keeps history, and our additions are separate files, so merges stay conflict-free.
- **Deleting upstream workflow files.** That would conflict with every upstream change to them. They are disabled in the repository's Actions settings instead (`mb1`).

## Manual steps

The steps are in the [step-by-step page](https://claude.ai/artifact/KhQXY5KJJJip5XK9MiqVQf), whose source is `pf/docs/operational-fork-plan-manual-steps.html`.

- **Before:** `mb1-branch-and-actions`:
  - create `privacyfence` from `a10b722` and make it the default branch;
  - disable the upstream workflows;
  - allow Actions to create pull requests.
- **After:** `ma1-first-release`:
  - the maintainer tags `v1.7.22-pf.1`;
  - make the package public;
  - check `docker pull`.

## Risks and open questions

- **`ghcr.io/navikt/mock-oauth2-server:2.1.10` behaves differently** (another tag, a different config key, or a userinfo without `email_verified`). The first pf-ci run fails at `check_oidc_sign_in` with the mock's log. The worker stops with `status=blocked` and reports the log, rather than switching providers.
- **`POST /api/profile/apikey` needs a different header** for cookie-authenticated calls. `check_api_key` fails with a 4xx. The worker reads `app/server/lib/requestUtils.ts` or `app/gen-server/ApiServer.ts:554-586` and adjusts the header only. If the endpoint is refused outright, it stops with `status=blocked`, because that would be a lock-out.
- **The arm64 runner label** `ubuntu-24.04-arm` may be unavailable to the organization. The dry run fails on the arm64 job. The worker stops with `status=blocked`; it never drops arm64 silently.
- **Workflows on a branch that is not the default** cannot be dispatched. During `/implement`, pf-ci runs on push to the phase branches; `pf-release.yml` and `pf-sync.yml` can only be dispatched after the feature PR merges into `privacyfence`. Their dry runs are in `manual_after` (`ma1`).

## Implementation manifest

```yaml
plan_slug: operational-fork
feature_branch: feature/operational-fork
max_parallel: 2
manual_steps_artifact: https://claude.ai/artifact/KhQXY5KJJJip5XK9MiqVQf
manual_steps_source: pf/docs/operational-fork-plan-manual-steps.html
manual_before:
  - id: mb1-branch-and-actions
    title: Create the privacyfence branch from v1.7.22, make it the default, disable the upstream workflows and let Actions open pull requests
    why: /implement opens its PR to privacyfence; upstream workflows would otherwise try to push to Docker Hub, deploy to Fly or run the CLA bot on our PRs; pf-sync.yml needs to open PRs
    done_when: https://github.com/privacyfence/grist-core shows privacyfence as the default branch at commit a10b722, the Actions page lists docker.yml, docker_latest.yml, fly-build.yml, fly-deploy.yml, fly-cleanup.yml, fly-destroy.yml, cla.yml, self-hosted.yml and translation_keys.yml as disabled, and Settings → Actions → General has "Allow GitHub Actions to create and approve pull requests" ticked
manual_after:
  - id: ma1-first-release
    title: Dry-run the release and sync workflows, tag v1.7.22-pf.1, make the package public and pull it
    why: Tags can only be pushed by the maintainer, package visibility is a setting, and the two workflows can only be dispatched once they are on the default branch
verify_after_merge:
  - python3 -m pip install -q -r pf/requirements-dev.txt && python3 -m pytest pf/tests -q && ruff check pf
final_checks:
  - pf/docs/operational-fork-plan.md and pf/docs/operational-fork-plan-manual-steps.html are deleted and nothing links to them
  - pf/CHANGELOG.md has entries under "## [Unreleased]" and no version heading
  - git diff --stat a10b7227365adfe2555be40ae87bb9741284c0ca..HEAD touches only .claude/, pf/ and .github/workflows/pf-*.yml
  - the pf-ci.yml run on the feature branch's head is green
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
      2. pf/requirements-dev.txt: pytest==8.4.2 and ruff==0.14.1. pf/ruff.toml: line-length = 120, target-version = "py312".
      3. pf/PATCHES.md with the two empty tables and the rule, exactly as the Design describes.
      4. pf/README.md with the sections listed in the Design. The release, sync and lock-out sections can say "added by this plan's later phases" for now; p6 completes them.
      5. .claude/toolkit.yaml: add pf/README.md to docs.must_read after README.md.
      6. pf/tests/test_repo_files.py: test_upstream_file_is_a_release_tag (pf/UPSTREAM matches ^v\d+\.\d+\.\d+\n?$) and test_upstream_matches_package_version (it equals "v" + package.json's version).
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
      2. pf/e2e/lockout_check.py: CheckFailed, Context, request(), the four check functions in order, and main() with argparse (--grist, --boot-key, --site, --email) and the output lines exactly as designed. Never print the boot key, the API key or a cookie.
      3. pf/e2e/run_lockout.sh exactly as the six steps describe, including the trap cleanup and masking. Make it executable (git update-index --chmod=+x).
      4. pf/tests/test_lockout_check.py, with a fake opener that returns canned responses per (method, path):
         - test_sign_in_ok, test_sign_in_wrong_email_fails;
         - test_api_key_ok, test_api_key_refused_fails;
         - test_boot_key_access_ok, test_boot_key_access_no_users_list_fails;
         - test_team_membership_ok, test_team_membership_role_missing_fails;
         - test_main_stops_at_first_failure_and_exits_1;
         - test_secrets_never_printed (capsys: neither the boot key nor the API key appear in the output).
      5. Run `python3 -m pytest pf/tests -q` and `ruff check pf`. Also run `bash -n pf/e2e/run_lockout.sh`.
    acceptance:
      - python3 -m pytest pf/tests -q passes, including every named test
      - bash -n pf/e2e/run_lockout.sh exits 0
      - grep -n "def check_oidc_sign_in" pf/e2e/lockout_check.py finds it

  - id: p3-ci
    title: pf-ci.yml builds the open-source image and runs the lock-out check
    depends_on: [p2-lockout-check]
    complexity: S
    touches:
      - .github/workflows/pf-ci.yml
    brief: |
      Read pf/docs/operational-fork-plan.md: "The image" and "CI".
      1. Write .github/workflows/pf-ci.yml as designed, with GVISOR_DIGEST as a workflow env. To find the digest, the first push of this phase has an extra step that prints `docker buildx imagetools inspect docker.io/gristlabs/gvisor-unprivileged:buster --format '{{json .Manifest.Digest}}'`, with GVISOR_DIGEST set to a placeholder that makes the build step skip. Read the run, put the digest into GVISOR_DIGEST, remove the extra step, and push again.
      2. Pin actions by full commit SHA with version comments: actions/checkout, docker/setup-buildx-action and docker/build-push-action. Use the SHAs of the versions upstream's .github/workflows/docker.yml names (v4, v3, v6), looked up with the GitHub MCP tools.
      3. Push, and read the run on the branch. Stop conditions, each a stop with status=blocked that reports the log:
         - check_oidc_sign_in fails (see Risks: the mock provider);
         - check_api_key fails with something other than a header problem (see Risks);
         - a "full edition" log line appears.
    acceptance:
      - the pf-ci.yml run on the pushed branch is green, with all four "ok:" lines in the log
      - grep -n "GRIST_EXT_FULL_EDITION_BASE_URL=" .github/workflows/pf-ci.yml finds the build argument
      - grep -n "GRIST_BUILD_CHANNEL=core" .github/workflows/pf-ci.yml finds it

  - id: p4-release
    title: pf-release.yml builds amd64 and arm64, checks, publishes to GHCR with provenance
    depends_on: [p3-ci]
    complexity: M
    touches:
      - .github/workflows/pf-release.yml
    brief: |
      Read pf/docs/operational-fork-plan.md: "Branches and versions", "The image" and "Release".
      1. Write .github/workflows/pf-release.yml with the jobs check, build and publish exactly as designed. Copy the by-digest build and manifest-list pattern from upstream's .github/workflows/docker.yml (build_and_push and publish jobs), with ghcr.io/privacyfence/grist-core as the only image and GITHUB_TOKEN for the GHCR login. Pin actions by SHA as in pf-ci.yml; add actions/upload-artifact, actions/download-artifact, docker/login-action, docker/metadata-action (only if used) and actions/attest-build-provenance.
      2. Use the same GVISOR_DIGEST as pf-ci.yml.
      3. This workflow cannot run before it is on privacyfence (Risks). Check it with `python3 -c "import yaml,sys; yaml.safe_load(open('.github/workflows/pf-release.yml'))"`, after `pip install pyyaml==6.0.2` in a throwaway virtualenv, and reread every job's `if:` against the dry-run rules.
    acceptance:
      - the YAML parses
      - grep -n "push-by-digest=true" .github/workflows/pf-release.yml finds it
      - grep -n "attest-build-provenance" .github/workflows/pf-release.yml finds it
      - grep -n "merge-base --is-ancestor" .github/workflows/pf-release.yml finds the branch check

  - id: p5-sync
    title: pf-sync.yml opens a pull request for each new upstream release
    depends_on: [p3-ci]
    complexity: S
    touches:
      - .github/workflows/pf-sync.yml
    brief: |
      Read pf/docs/operational-fork-plan.md, section "Upstream sync".
      1. Write .github/workflows/pf-sync.yml with the six steps exactly as designed, using `gh` with GH_TOKEN set to the GITHUB_TOKEN. Pin actions/checkout by SHA as in pf-ci.yml.
      2. Check that the YAML parses, as p4 step 3 does. Also check step 1's sed expression locally: feed it `printf 'x\trefs/tags/v1.7.9\nx\trefs/tags/v1.7.22\nx\trefs/tags/v1.7.22^{}\nx\trefs/tags/v2.0.0-rc1\n'` and confirm the pipeline prints v1.7.22.
    acceptance:
      - the YAML parses
      - grep -n "gh workflow run pf-ci.yml" .github/workflows/pf-sync.yml finds the dispatch
      - grep -n "needs a manual merge" .github/workflows/pf-sync.yml finds the conflict issue

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
      1. pf/README.md: complete the release section (the changelog PR renaming "## [Unreleased]" to "## [X.Y.Z-pf.N] - YYYY-MM-DD" with a new empty Unreleased above it; the maintainer pushes `vX.Y.Z-pf.N`; the first time, set the package public in its settings; the dry run), the sync section (what pf-sync.yml does, reviewing its PR, the lock-out check as the gate, the manual-merge issue and PATCHES.md) and the lock-out check section (the four checks, the image settings checks, what a failure means and how to record a revert). Add the gvisor fallback.
      2. pf/CHANGELOG.md, "## [Unreleased]", "### Added":
         - "- **Open-source image.** `ghcr.io/privacyfence/grist-core`, built from grist-core with no full-edition extensions and the full-edition switch turned off, for amd64 and arm64, with build provenance."
         - "- **Lock-out check.** Every build signs in through OIDC and uses API keys, the boot key and the team-site access API; a build where any of them is locked fails."
         - "- **Upstream sync.** A weekly workflow opens a pull request for each new upstream release."
      3. Delete pf/docs/operational-fork-plan.md and pf/docs/operational-fork-plan-manual-steps.html; `grep -rn --exclude-dir=.git "operational-fork-plan" pf .claude .github` finds nothing.
    acceptance:
      - test ! -e pf/docs/operational-fork-plan.md
      - grep -rn --exclude-dir=.git "operational-fork-plan" pf .claude .github finds nothing
      - grep -n "Lock-out check" pf/CHANGELOG.md finds the entry
```
