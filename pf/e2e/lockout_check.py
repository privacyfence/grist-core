#!/usr/bin/env python3
"""Lock-out check: proves that a built Grist image has nothing locked that the suite needs.

Standard library only. The boot key comes from the environment (PF_BOOT_KEY), never from the command line.
Nothing this script prints contains the boot key, the API key or a cookie.
"""

import argparse
import http.cookiejar
import json
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field

FORBIDDEN_FEATURES = ("maxUsersPerOrg", "maxApiCallsPerOrgMonth", "baseMaxRowsPerDocument")
TIMEOUT = 30


class CheckFailed(Exception):
    pass


@dataclass
class Context:
    opener: object
    base: str
    boot_key: str
    site: str
    email: str
    api_key: str = ""
    scratch: dict = field(default_factory=dict)


def request(ctx, method, path, *, headers=None, json_body=None, raise_for_status=True):
    """Send one request and return (status, body). JSON bodies always carry a JSON content type."""
    all_headers = dict(headers or {})
    data = None
    if json_body is not None:
        data = json.dumps(json_body).encode()
        all_headers["Content-Type"] = "application/json"
    req = urllib.request.Request(ctx.base + path, data=data, headers=all_headers, method=method)
    try:
        with ctx.opener.open(req, timeout=TIMEOUT) as resp:
            status, body = resp.status, resp.read()
    except urllib.error.HTTPError as err:
        status, body = err.code, err.read()
    except urllib.error.URLError as err:
        raise CheckFailed(f"{method} {path} failed: {err.reason}") from err
    if raise_for_status and status >= 400:
        raise CheckFailed(f"{method} {path} answered {status}")
    return status, body


def _json(body, what):
    try:
        return json.loads(body)
    except ValueError as err:
        raise CheckFailed(f"{what} is not JSON") from err


def _boot(ctx):
    return {"x-boot-key": ctx.boot_key}


def _expect_status(status, expected, method, path):
    if status != expected:
        raise CheckFailed(f"{method} {path} answered {status}, expected {expected}")


def check_boot_key_access(ctx):
    path = f"/api/orgs/{ctx.site}/access"
    status, body = request(ctx, "GET", path, headers=_boot(ctx))
    _expect_status(status, 200, "GET", path)
    data = _json(body, "access response")
    if not isinstance(data, dict) or not isinstance(data.get("users"), list):
        raise CheckFailed("access response has no users list")


def check_free_plan_limits(ctx):
    path = f"/api/orgs/{ctx.site}"
    status, body = request(ctx, "GET", path, headers=_boot(ctx))
    _expect_status(status, 200, "GET", path)
    org = _json(body, "org response")
    try:
        product = org["billingAccount"]["product"]
        name, features = product["name"], product["features"]
    except (KeyError, TypeError) as err:
        raise CheckFailed("org JSON has no billingAccount.product") from err
    if name != "Free":
        raise CheckFailed(f"product is {name!r}, expected 'Free'")
    if not isinstance(features, dict):
        raise CheckFailed("product features are not an object")
    limited = [key for key in FORBIDDEN_FEATURES if key in features]
    if limited:
        raise CheckFailed("free plan has limits: " + ", ".join(limited))


def check_team_membership(ctx):
    path = f"/api/orgs/{ctx.site}/access"
    wanted = {"newcomer@example.com": "editors", ctx.email: "editors"}
    status, _ = request(ctx, "PATCH", path, headers=_boot(ctx), json_body={"delta": {"users": wanted}})
    _expect_status(status, 200, "PATCH", path)
    status, body = request(ctx, "GET", path, headers=_boot(ctx))
    _expect_status(status, 200, "GET", path)
    access = _json(body, "access response")
    users = access.get("users") if isinstance(access, dict) else None
    if not isinstance(users, list):
        raise CheckFailed("access response has no users list")
    roles = {u.get("email"): u.get("access") for u in users if isinstance(u, dict)}
    for email in wanted:
        if roles.get(email) != "editors":
            raise CheckFailed(f"{email} is not an editor of the team site")


def build_session_opener():
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar)), jar


def check_oidc_sign_in(ctx):
    if "jar" not in ctx.scratch:
        ctx.opener, ctx.scratch["jar"] = build_session_opener()
    # The last redirect may land on a page that answers an error; only the profile below decides.
    request(ctx, "GET", "/login?next=/", raise_for_status=False)
    if not any("localhost" in cookie.domain for cookie in ctx.scratch["jar"]):
        raise CheckFailed("no session cookie: check for a Domain=localhost cookie")
    status, body = request(ctx, "GET", "/api/profile/user")
    _expect_status(status, 200, "GET", "/api/profile/user")
    profile = _json(body, "profile")
    if not isinstance(profile, dict):
        raise CheckFailed("profile response is not an object")
    email = profile.get("email")
    if email != ctx.email:
        raise CheckFailed(f"signed in as {email!r}, expected {ctx.email!r}")


def check_api_key(ctx):
    path = "/api/profile/apikey"
    status, body = request(ctx, "POST", path, headers={"X-Requested-With": "XMLHttpRequest"}, json_body={"force": True})
    _expect_status(status, 200, "POST", path)
    key = body.decode("utf-8", "replace").strip()
    if not re.fullmatch(r"[0-9a-f]{40}", key):
        raise CheckFailed("API key is not 40 hex characters")
    ctx.api_key = key


def check_api_key_use(ctx):
    # A fresh opener without cookies: only the Bearer header may authenticate these requests.
    ctx.opener = urllib.request.build_opener()
    auth = {"Authorization": f"Bearer {ctx.api_key}"}
    path = f"/api/orgs/{ctx.site}/workspaces"
    status, body = request(ctx, "POST", path, headers=auth, json_body={"name": "lockout"})
    _expect_status(status, 200, "POST", path)
    ws_id = _json(body, "workspace response")
    if not isinstance(ws_id, int) or isinstance(ws_id, bool):
        raise CheckFailed("workspace id is not an integer")
    path = f"/api/workspaces/{ws_id}/docs"
    status, body = request(ctx, "POST", path, headers=auth, json_body={"name": "lockout"})
    _expect_status(status, 200, "POST", path)
    doc_id = _json(body, "doc response")
    if not isinstance(doc_id, str) or not doc_id:
        raise CheckFailed("doc id is not a string")
    path = f"/api/docs/{doc_id}/tables"
    status, _ = request(ctx, "GET", path, headers=auth)
    _expect_status(status, 200, "GET", path)


def check_no_personal_org(ctx):
    """With GRIST_PERSONAL_ORGS=false, the signed-in user sees the team site and no personal org."""
    status, body = request(ctx, "GET", "/api/orgs")
    _expect_status(status, 200, "GET", "/api/orgs")
    orgs = _json(body, "orgs response")
    if not isinstance(orgs, list) or not all(isinstance(org, dict) for org in orgs):
        raise CheckFailed("orgs response is not a list of objects")
    personal = [org for org in orgs if org.get("owner")]
    if personal:
        raise CheckFailed(f"the user sees {len(personal)} personal org(s)")
    domains = sorted(str(org.get("domain")) for org in orgs)
    if domains != [ctx.site]:
        raise CheckFailed(f"the user sees the sites {domains}, expected only {ctx.site!r}")


def check_no_org_creation(ctx):
    """With GRIST_ORG_CREATION_ANYONE=false, a signed-in user cannot create a site."""
    path = "/api/orgs"
    status, _ = request(
        ctx,
        "POST",
        path,
        headers={"X-Requested-With": "XMLHttpRequest"},
        json_body={"name": "lockout-new", "domain": "lockout-new"},
        raise_for_status=False,
    )
    _expect_status(status, 403, "POST", path)


CHECKS = [
    check_boot_key_access,
    check_free_plan_limits,
    check_team_membership,
    check_oidc_sign_in,
    check_api_key,
    check_api_key_use,
]

# Run after check_oidc_sign_in (they need its session), with --suite-settings only.
SUITE_SETTINGS_CHECKS = [
    check_no_personal_org,
    check_no_org_creation,
]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--grist", required=True, help="base URL of Grist")
    parser.add_argument("--site", required=True, help="team site subdomain")
    parser.add_argument("--email", required=True, help="email the mock identity provider signs in")
    parser.add_argument(
        "--suite-settings",
        action="store_true",
        help="Grist runs with GRIST_PERSONAL_ORGS=false and GRIST_ORG_CREATION_ANYONE=false: also check those",
    )
    args = parser.parse_args(argv)
    boot_key = os.environ.get("PF_BOOT_KEY", "")
    if not boot_key:
        print("FAIL: setup: PF_BOOT_KEY is not set")
        return 1
    ctx = Context(
        opener=urllib.request.build_opener(),
        base=args.grist.rstrip("/"),
        boot_key=boot_key,
        site=args.site,
        email=args.email,
    )
    checks = list(CHECKS)
    if args.suite_settings:
        names = [check.__name__ for check in checks]
        at = names.index("check_oidc_sign_in") + 1
        checks[at:at] = SUITE_SETTINGS_CHECKS
    for check in checks:
        name = check.__name__.removeprefix("check_")
        try:
            check(ctx)
        except CheckFailed as err:
            print(f"FAIL: {name}: {err}")
            return 1
        print(f"ok: {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
