"""Auth tests: login/logout/session cookie/CSRF/rate limit."""
from httpx import ASGITransport, AsyncClient

from app.main import app


async def test_login_ok_sets_cookie(user):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/auth/login",
                            json={"username": "tester", "password": "testpass"})
        assert resp.status_code == 200
        assert "fund2_session" in resp.cookies
        body = resp.json()
        assert body["username"] == "tester"
        assert body["csrf_token"]

        me = await c.get("/auth/me")
        assert me.status_code == 200
        assert me.json()["username"] == "tester"


async def test_login_wrong_password(user):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/auth/login",
                            json={"username": "tester", "password": "wrong"})
        assert resp.status_code == 401


async def test_login_unknown_user(user):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/auth/login",
                            json={"username": "ghost", "password": "x"})
        assert resp.status_code == 401


async def test_me_requires_session(client):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/auth/me")
        assert resp.status_code == 401


async def test_logout_invalidates_session(client):
    csrf = (await client.get("/auth/me")).json()["csrf_token"]
    resp = await client.post("/auth/logout", headers={"x-csrf-token": csrf})
    assert resp.status_code == 200
    assert (await client.get("/auth/me")).status_code == 401


async def test_post_orders_requires_csrf(client, tick_2000):
    del client.headers["x-csrf-token"]  # fixture memasang token global; test ini justru tanpa CSRF
    resp = await client.post(
        "/orders",
        json={"symbol": "XAUUSD", "side": "BUY", "volume": 0.1, "sl": 1998, "tp": 2005},
    )
    assert resp.status_code == 403


async def test_login_rate_limit(user):
    from app.auth import reset_login_rate_limit

    reset_login_rate_limit()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        codes = []
        for _ in range(12):
            resp = await c.post("/auth/login",
                                json={"username": "tester", "password": "wrong"})
            codes.append(resp.status_code)
        assert codes.count(429) >= 1  # limited after 10 attempts/min
