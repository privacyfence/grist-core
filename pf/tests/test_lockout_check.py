import http.cookiejar
import importlib.util
import io
import json
import urllib.error
from pathlib import Path
from urllib.parse import urlsplit

import pytest

SPEC = importlib.util.spec_from_file_location(
    "lockout_check", Path(__file__).resolve().parents[1] / "e2e" / "lockout_check.py"
)
lc = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(lc)

BOOT_KEY = "b00t" * 8
API_KEY = "ab12" * 10
EMAIL = "lockout@example.com"


class Resp:
    def __init__(self, status, body):
        self.status = status
        self._body = body.encode() if isinstance(body, str) else body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def ok(body):
    return Resp(200, json.dumps(body))


class FakeOpener:
    """Returns canned responses per (method, path); a status >= 400 is raised as HTTPError, as urllib does."""

    def __init__(self, routes):
        self.routes = routes
        self.requests = []

    def open(self, req, timeout=None):
        path = urlsplit(req.full_url).path
        self.requests.append(req)
        resp = self.routes.get((req.get_method(), path))
        if resp is None:
            resp = Resp(404, "{}")
        if resp.status >= 400:
            raise urllib.error.HTTPError(req.full_url, resp.status, "err", {}, io.BytesIO(resp.read()))
        return resp


def make_ctx(routes, **kwargs):
    ctx = lc.Context(opener=FakeOpener(routes), base="http://grist", boot_key=BOOT_KEY, site="team", email=EMAIL)
    for key, value in kwargs.items():
        setattr(ctx, key, value)
    return ctx


def session_jar(with_cookie=True):
    jar = http.cookiejar.CookieJar()
    if with_cookie:
        jar.set_cookie(
            http.cookiejar.Cookie(
                0, "sid", "x", None, False, "localhost", True, False, "/", True, False, None, True, None, None, {}
            )
        )
    return jar


def free_org(name="Free", features=None):
    return {"billingAccount": {"product": {"name": name, "features": features if features is not None else {}}}}


def test_boot_key_access_ok():
    ctx = make_ctx({("GET", "/api/orgs/team/access"): ok({"users": []})})
    lc.check_boot_key_access(ctx)
    assert ctx.opener.requests[0].get_header("X-boot-key") == BOOT_KEY


def test_boot_key_access_no_users_list_fails():
    ctx = make_ctx({("GET", "/api/orgs/team/access"): ok({"x": 1})})
    with pytest.raises(lc.CheckFailed, match="users list"):
        lc.check_boot_key_access(ctx)


def test_free_plan_ok():
    lc.check_free_plan_limits(make_ctx({("GET", "/api/orgs/team"): ok(free_org())}))


def test_free_plan_limit_key_fails():
    org = free_org(features={"maxUsersPerOrg": 3})
    with pytest.raises(lc.CheckFailed, match="maxUsersPerOrg"):
        lc.check_free_plan_limits(make_ctx({("GET", "/api/orgs/team"): ok(org)}))


def test_free_plan_missing_product_fails():
    with pytest.raises(lc.CheckFailed, match="org JSON has no billingAccount.product"):
        lc.check_free_plan_limits(make_ctx({("GET", "/api/orgs/team"): ok({"id": 1})}))


def membership_routes(users):
    return {("PATCH", "/api/orgs/team/access"): ok({}), ("GET", "/api/orgs/team/access"): ok({"users": users})}


def test_team_membership_ok():
    users = [{"email": "newcomer@example.com", "access": "editors"}, {"email": EMAIL, "access": "editors"}]
    ctx = make_ctx(membership_routes(users))
    lc.check_team_membership(ctx)
    sent = json.loads(ctx.opener.requests[0].data)
    assert sent == {"delta": {"users": {"newcomer@example.com": "editors", EMAIL: "editors"}}}


def test_team_membership_role_missing_fails():
    users = [{"email": "newcomer@example.com", "access": "editors"}]
    with pytest.raises(lc.CheckFailed, match=EMAIL):
        lc.check_team_membership(make_ctx(membership_routes(users)))


def sign_in_ctx(email=EMAIL, final_hop=None, jar=None):
    final_hop = final_hop or Resp(403, "no")
    routes = {("GET", "/login"): final_hop, ("GET", "/api/profile/user"): ok({"email": email})}
    return make_ctx(routes, scratch={"jar": jar if jar is not None else session_jar()})


def test_sign_in_ok_even_if_final_hop_403():
    lc.check_oidc_sign_in(sign_in_ctx())


def test_sign_in_wrong_email_fails():
    with pytest.raises(lc.CheckFailed, match="signed in as"):
        lc.check_oidc_sign_in(sign_in_ctx(email="other@example.com"))


def test_sign_in_without_cookie_fails():
    with pytest.raises(lc.CheckFailed, match="no session cookie"):
        lc.check_oidc_sign_in(sign_in_ctx(jar=session_jar(with_cookie=False)))


def test_sign_in_profile_not_object_fails():
    ctx = sign_in_ctx()
    ctx.opener.routes[("GET", "/api/profile/user")] = ok(["x"])
    with pytest.raises(lc.CheckFailed, match="profile response is not an object"):
        lc.check_oidc_sign_in(ctx)


def test_team_membership_access_not_object_fails():
    ctx = make_ctx({("PATCH", "/api/orgs/team/access"): ok({}), ("GET", "/api/orgs/team/access"): ok([1])})
    with pytest.raises(lc.CheckFailed, match="no users list"):
        lc.check_team_membership(ctx)


def test_api_key_plain_text_ok():
    ctx = make_ctx({("POST", "/api/profile/apikey"): Resp(200, API_KEY + "\n")})
    lc.check_api_key(ctx)
    assert ctx.api_key == API_KEY
    req = ctx.opener.requests[0]
    assert req.get_header("X-requested-with") == "XMLHttpRequest"
    assert json.loads(req.data) == {"force": True}


def test_api_key_refused_fails():
    ctx = make_ctx({("POST", "/api/profile/apikey"): Resp(403, "nope")})
    with pytest.raises(lc.CheckFailed, match="403"):
        lc.check_api_key(ctx)


def use_routes(workspace=None):
    workspace = workspace or Resp(200, "7")
    return {
        ("POST", "/api/orgs/team/workspaces"): workspace,
        ("POST", "/api/workspaces/7/docs"): Resp(200, '"docabc"'),
        ("GET", "/api/docs/docabc/tables"): ok({"tables": []}),
    }


def use_ctx(monkeypatch, routes):
    """A context whose session opener has a cookie; check_api_key_use must build its own cookie-less opener."""
    fresh = FakeOpener(routes)
    built = []

    def build_opener(*handlers):
        built.append(handlers)
        return fresh

    monkeypatch.setattr(lc.urllib.request, "build_opener", build_opener)
    ctx = make_ctx({}, api_key=API_KEY, scratch={"jar": session_jar()})
    return ctx, fresh, built


def test_api_key_use_ok(monkeypatch):
    ctx, fresh, _ = use_ctx(monkeypatch, use_routes())
    lc.check_api_key_use(ctx)
    assert all(r.get_header("Authorization") == f"Bearer {API_KEY}" for r in fresh.requests)
    assert len(fresh.requests) == 3


def test_api_key_use_sends_no_cookie(monkeypatch):
    ctx, fresh, built = use_ctx(monkeypatch, use_routes())
    session_opener = ctx.opener
    lc.check_api_key_use(ctx)
    assert built == [()]  # a plain opener: no cookie processor
    assert ctx.opener is fresh and ctx.opener is not session_opener
    assert session_opener.requests == []
    assert len(fresh.requests) == 3
    assert all(r.get_header("Cookie") is None for r in fresh.requests)


def test_api_key_use_workspace_refused_fails(monkeypatch):
    ctx, _, _ = use_ctx(monkeypatch, use_routes(workspace=Resp(403, "no")))
    with pytest.raises(lc.CheckFailed, match="403"):
        lc.check_api_key_use(ctx)


def test_json_body_sends_content_type():
    ctx = make_ctx({("POST", "/x"): ok({})})
    lc.request(ctx, "POST", "/x", json_body={"a": 1})
    assert ctx.opener.requests[0].get_header("Content-type") == "application/json"


def test_missing_boot_key_env_fails(monkeypatch, capsys):
    monkeypatch.delenv("PF_BOOT_KEY", raising=False)
    assert lc.main(["--grist", "http://grist", "--site", "team", "--email", EMAIL]) == 1
    assert capsys.readouterr().out == "FAIL: setup: PF_BOOT_KEY is not set\n"


def patch_checks(monkeypatch, names_to_fail=()):
    calls = []

    def make(name):
        def check(ctx):
            calls.append(name)
            if name in names_to_fail:
                raise lc.CheckFailed("boom")

        check.__name__ = "check_" + name
        return check

    monkeypatch.setattr(lc, "CHECKS", [make(n) for n in ("one", "two", "three")])
    monkeypatch.setenv("PF_BOOT_KEY", BOOT_KEY)
    return calls


ARGV = ["--grist", "http://grist", "--site", "team", "--email", EMAIL]


def test_main_stops_at_first_failure_and_exits_1(monkeypatch, capsys):
    calls = patch_checks(monkeypatch, names_to_fail=("two",))
    assert lc.main(ARGV) == 1
    assert calls == ["one", "two"]
    assert capsys.readouterr().out.splitlines() == ["ok: one", "FAIL: two: boom"]


def test_main_all_ok_exits_0(monkeypatch, capsys):
    patch_checks(monkeypatch)
    assert lc.main(ARGV) == 0
    assert capsys.readouterr().out.splitlines() == ["ok: one", "ok: two", "ok: three"]


def test_secrets_never_printed(monkeypatch, capsys):
    monkeypatch.setenv("PF_BOOT_KEY", BOOT_KEY)
    routes = {
        ("GET", "/api/orgs/team/access"): ok({"users": []}),
        ("GET", "/api/orgs/team"): ok(free_org()),
        ("POST", "/api/profile/apikey"): Resp(200, API_KEY),
    }
    opener = FakeOpener(routes)
    monkeypatch.setattr(lc.urllib.request, "build_opener", lambda *a: opener)
    assert lc.main(ARGV) == 1  # stops at the membership check: no PATCH route
    out = capsys.readouterr()
    assert BOOT_KEY not in out.out + out.err
    assert API_KEY not in out.out + out.err
    ctx = make_ctx({("POST", "/api/profile/apikey"): Resp(403, API_KEY)}, api_key=API_KEY)
    with pytest.raises(lc.CheckFailed) as err:
        lc.check_api_key(ctx)
    assert API_KEY not in str(err.value)


def test_secrets_never_printed_when_api_key_use_fails(monkeypatch, capsys):
    monkeypatch.setenv("PF_BOOT_KEY", BOOT_KEY)
    jar = session_jar()
    session = FakeOpener(
        {
            ("GET", "/api/orgs/team/access"): ok(
                {"users": [{"email": e, "access": "editors"} for e in ("newcomer@example.com", EMAIL)]}
            ),
            ("PATCH", "/api/orgs/team/access"): ok({}),
            ("GET", "/api/orgs/team"): ok(free_org()),
            ("GET", "/login"): Resp(403, "no"),
            ("GET", "/api/profile/user"): ok({"email": EMAIL}),
            ("POST", "/api/profile/apikey"): Resp(200, API_KEY),
        }
    )
    failing = FakeOpener({("POST", "/api/orgs/team/workspaces"): Resp(403, f"{API_KEY} {BOOT_KEY}")})
    openers = iter([session, failing])
    monkeypatch.setattr(lc.urllib.request, "build_opener", lambda *a: next(openers))
    monkeypatch.setattr(lc, "build_session_opener", lambda: (session, jar))
    assert lc.main(ARGV) == 1
    out = capsys.readouterr()
    text = out.out + out.err
    assert "ok: api_key" in text and "FAIL: api_key_use" in text
    assert BOOT_KEY not in text
    assert API_KEY not in text


def orgs_ctx(orgs):
    return make_ctx({("GET", "/api/orgs"): ok(orgs)})


def test_no_personal_org_ok():
    lc.check_no_personal_org(orgs_ctx([{"domain": "team", "owner": None}]))


def test_no_personal_org_personal_org_fails():
    ctx = orgs_ctx([{"domain": "team", "owner": None}, {"domain": None, "owner": {"id": 5}}])
    with pytest.raises(lc.CheckFailed, match="personal org"):
        lc.check_no_personal_org(ctx)


def test_no_personal_org_other_site_fails():
    ctx = orgs_ctx([{"domain": "team", "owner": None}, {"domain": "other", "owner": None}])
    with pytest.raises(lc.CheckFailed, match="expected only 'team'"):
        lc.check_no_personal_org(ctx)


def test_no_personal_org_no_team_site_fails():
    with pytest.raises(lc.CheckFailed, match="expected only 'team'"):
        lc.check_no_personal_org(orgs_ctx([]))


def test_no_personal_org_not_a_list_fails():
    with pytest.raises(lc.CheckFailed, match="not a list"):
        lc.check_no_personal_org(orgs_ctx({"error": "x"}))


def test_no_org_creation_refused_ok():
    ctx = make_ctx({("POST", "/api/orgs"): Resp(403, '{"error": "no"}')})
    lc.check_no_org_creation(ctx)
    assert ctx.opener.requests[0].get_header("X-requested-with") == "XMLHttpRequest"


def test_no_org_creation_allowed_fails():
    ctx = make_ctx({("POST", "/api/orgs"): ok(12)})
    with pytest.raises(lc.CheckFailed, match="answered 200, expected 403"):
        lc.check_no_org_creation(ctx)


def test_main_suite_settings_runs_extra_checks_after_sign_in(monkeypatch, capsys):
    calls = []

    def make(name):
        def check(ctx):
            calls.append(name)

        check.__name__ = "check_" + name
        return check

    monkeypatch.setattr(lc, "CHECKS", [make(n) for n in ("boot", "oidc_sign_in", "api_key")])
    monkeypatch.setattr(lc, "SUITE_SETTINGS_CHECKS", [make(n) for n in ("no_personal_org", "no_org_creation")])
    monkeypatch.setenv("PF_BOOT_KEY", BOOT_KEY)
    assert lc.main(ARGV) == 0
    assert calls == ["boot", "oidc_sign_in", "api_key"]
    calls.clear()
    assert lc.main([*ARGV, "--suite-settings"]) == 0
    assert calls == ["boot", "oidc_sign_in", "no_personal_org", "no_org_creation", "api_key"]
