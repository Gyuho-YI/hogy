"""cli.py 의 KRX 로그인 사전 점검(종료 코드 약속: 3 로그인, 4 접속) 검증."""
import sys
import types

import pytest
import requests

import cli


def _fake_pykrx(monkeypatch, session=None, raise_exc=None):
    auth = types.ModuleType("pykrx.website.comm.auth")

    def get_auth_session():
        if raise_exc:
            raise raise_exc
        return session
    auth.get_auth_session = get_auth_session
    for n in ["pykrx", "pykrx.website", "pykrx.website.comm", "pykrx.stock"]:
        monkeypatch.setitem(sys.modules, n, types.ModuleType(n))
    monkeypatch.setitem(sys.modules, "pykrx.website.comm.auth", auth)


def test_자격증명_없으면_3(monkeypatch):
    monkeypatch.delenv("KRX_ID", raising=False)
    monkeypatch.delenv("KRX_PW", raising=False)
    assert cli.ensure_krx_login() == cli.EXIT_KRX_LOGIN


@pytest.mark.parametrize("session,exc,expected", [
    (object(), None, 0),                                         # 로그인 성공
    (None, None, cli.EXIT_KRX_LOGIN),                            # 아이디/비번 오류
    (None, requests.ConnectionError("down"), cli.EXIT_KRX_NETWORK),  # 접속 불가
])
def test_로그인_결과별_종료코드(monkeypatch, session, exc, expected):
    monkeypatch.setenv("KRX_ID", "me")
    monkeypatch.setenv("KRX_PW", "pw")
    _fake_pykrx(monkeypatch, session=session, raise_exc=exc)
    assert cli.ensure_krx_login() == expected
