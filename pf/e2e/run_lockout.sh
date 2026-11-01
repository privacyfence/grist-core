#!/usr/bin/env bash
# Lock-out check runner: bash pf/e2e/run_lockout.sh <image>
# Needs MOCK_OIDC_IMAGE in the environment. Never enable shell tracing here: it would print the boot key.
set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "usage: $0 <image>" >&2
  exit 2
fi
IMAGE="$1"
: "${MOCK_OIDC_IMAGE:?MOCK_OIDC_IMAGE is not set}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
cd "$ROOT"

PERSIST_VOLUME=pf-lockout-persist

cleanup() {
  status=$?
  if [ "$status" -ne 0 ]; then
    echo "=== lock-out check failed; container logs follow ==="
    echo "--- grist ---"
    docker logs grist 2>&1 || true
    echo "--- mock-oidc ---"
    docker logs mock-oidc 2>&1 || true
  fi
  docker rm -f grist mock-oidc >/dev/null 2>&1 || true
  docker volume rm -f "$PERSIST_VOLUME" >/dev/null 2>&1 || true
  exit "$status"
}
trap cleanup EXIT

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

# 1. Image report.
echo "== image report: $IMAGE"
env_list="$(docker image inspect --format '{{range .Config.Env}}{{println .}}{{end}}' "$IMAGE")"
printf '%s\n' "$env_list" | grep -qx 'GRIST_EXT_FULL_EDITION_BASE_URL=' \
  || fail "image env lacks GRIST_EXT_FULL_EDITION_BASE_URL= (empty)"
printf '%s\n' "$env_list" | grep -qx 'GRIST_ALLOW_AUTOMATIC_VERSION_CHECKING=false' \
  || fail "image env lacks GRIST_ALLOW_AUTOMATIC_VERSION_CHECKING=false"
echo "ok: image env"
# Each test echoes its label first, so a failure names the failing item (the output is in the CI log).
docker run --rm --entrypoint sh "$IMAGE" -c '
  echo "image contents: /grist/ext/app must not exist" &&    test ! -e /grist/ext/app &&
  echo "image contents: /grist/ext/assets must not exist" && test ! -e /grist/ext/assets &&
  echo "image contents: /grist/_build/ext must not exist" && test ! -e /grist/_build/ext &&
  echo "image contents: build channel must be core" &&  grep -q "channel = \"core\"" /grist/_build/app/common/version.js
' \
  || fail "image contents: the last 'image contents:' line above names the failing item"
echo "ok: image contents"

# 2. The mock identity provider.
docker run -d --name mock-oidc --network host \
  -e SERVER_PORT=8080 -e JSON_CONFIG="$(cat pf/e2e/mock-oidc.json)" "$MOCK_OIDC_IMAGE" >/dev/null

# 3. Grist. start_grist [docker run options...] starts the image with the settings every pass shares.
PF_BOOT_KEY="$(openssl rand -hex 16)"
echo "::add-mask::$PF_BOOT_KEY"
export PF_BOOT_KEY
start_grist() {
  GRIST_BOOT_KEY="$PF_BOOT_KEY" docker run -d --name grist --network host \
    -e APP_HOME_URL=http://localhost:8484 \
    -e GRIST_SINGLE_ORG=team \
    -e GRIST_ADMIN_EMAIL=admin@example.com \
    -e GRIST_IN_SERVICE=true \
    -e GRIST_FORCE_LOGIN=true \
    -e GRIST_BOOT_KEY \
    -e GRIST_SESSION_SECRET="$(openssl rand -hex 16)" \
    -e GRIST_OIDC_IDP_ISSUER=http://localhost:8080/default \
    -e GRIST_OIDC_IDP_CLIENT_ID=grist \
    -e GRIST_OIDC_IDP_CLIENT_SECRET=secret \
    -e GRIST_OIDC_IDP_SKIP_END_SESSION_ENDPOINT=true \
    "$@" \
    "$IMAGE" >/dev/null
}

# 4. wait_grist <what>: wait for Grist, up to 180 s.
wait_grist() {
  local ready=0
  for _ in $(seq 1 90); do
    if curl -fsS http://localhost:8484/status >/dev/null 2>&1; then
      ready=1
      break
    fi
    sleep 2
  done
  [ "$ready" -eq 1 ] || fail "$1: Grist did not answer /status within 180 s"
}

check_logs() {
  if docker logs grist 2>&1 | grep -qi 'full edition'; then
    fail "$1: Grist's log mentions the full edition"
  fi
  echo "ok: logs"
}

# 5. Pass 1, default settings, no volume. The boot key travels in the environment only.
echo "== pass 1: default settings"
start_grist
wait_grist "pass 1"
python3 pf/e2e/lockout_check.py --grist http://localhost:8484 --site team --email lockout@example.com
check_logs "pass 1"
docker rm -f grist >/dev/null

# 6. Pass 2, the privacyfence-suite settings: no personal orgs, no site creation by users,
# on a fresh /persist volume, then again after a restart on the same volume.
echo "== pass 2: GRIST_PERSONAL_ORGS=false, GRIST_ORG_CREATION_ANYONE=false, fresh /persist volume"
docker volume rm -f "$PERSIST_VOLUME" >/dev/null 2>&1 || true
docker volume create "$PERSIST_VOLUME" >/dev/null
start_grist \
  -e GRIST_PERSONAL_ORGS=false \
  -e GRIST_ORG_CREATION_ANYONE=false \
  -v "$PERSIST_VOLUME:/persist"
wait_grist "pass 2, fresh volume"
python3 pf/e2e/lockout_check.py --grist http://localhost:8484 --site team --email lockout@example.com --suite-settings
check_logs "pass 2, fresh volume"
echo "== pass 2: restart on the same volume"
docker restart grist >/dev/null
wait_grist "pass 2, after restart"
python3 pf/e2e/lockout_check.py --grist http://localhost:8484 --site team --email lockout@example.com --suite-settings
check_logs "pass 2, after restart"
