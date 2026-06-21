"""사용자 KIS 자격정보의 단일 조회 계층(배포·개발 동일 흐름).

API 방식: KIS OpenAPI 앱키/시크릿 + 계좌번호만 필요(간편인증 PIN·계좌비밀번호 불필요).
- 배포(app exe, frozen): Windows 자격증명 관리자(Credential Manager) — DPAPI(사용자+기기 키)로 암호화.
- 개발(비-frozen): keyring 이 비어있으면 data-pipeline/.env 로 폴백
  (KIS_APP_KEY / KIS_SECRET_KEY / ACCOUNT_NUMBER) → 개발에서 GUI·파이프라인을 그대로 띄우면 흐른다.
- 평문 파일·레포에 저장하지 않는다(.env gitignore). 다른 사용자는 각자 PC 에 본인 것만.
"""
import os
import sys
import json

import keyring

SERVICE = "KIS-Portfolio-Report"
ACCOUNT = "credentials"
KEYS = ("APP_KEY", "APP_SECRET", "ACC_NUMBER")

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEV_ENV = os.path.join(_REPO, "data-pipeline", ".env")    # 개발 폴백(.env)


def save(app_key, app_secret, acc_number):
    keyring.set_password(SERVICE, ACCOUNT, json.dumps({
        "APP_KEY": app_key.strip(),
        "APP_SECRET": app_secret.strip(),
        "ACC_NUMBER": acc_number.strip(),
    }))


def _keyring_raw():
    raw = keyring.get_password(SERVICE, ACCOUNT)
    if raw:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
    return {}


def load():
    """{APP_KEY, APP_SECRET, ACC_NUMBER} | None. keyring 우선, 개발 시 .env/jwt 폴백."""
    d = _keyring_raw()
    if all(d.get(k) for k in KEYS):
        return {k: d[k] for k in KEYS}
    return _dev_fallback(d)


def _dev_fallback(kr):
    """개발 전용(비-frozen): data-pipeline/.env 에서 APP_KEY/SECRET/계좌번호 로드."""
    if getattr(sys, "frozen", False):
        return None
    try:
        from dotenv import dotenv_values
        env = dotenv_values(_DEV_ENV)
    except Exception:
        env = {}
    out = {
        "APP_KEY": env.get("KIS_APP_KEY"),
        "APP_SECRET": env.get("KIS_SECRET_KEY"),
        "ACC_NUMBER": env.get("ACCOUNT_NUMBER") or kr.get("ACC_NUMBER"),  # .env 우선, 레거시 keyring 보조
    }
    return out if all(out.get(k) for k in KEYS) else None


def clear():
    try:
        keyring.delete_password(SERVICE, ACCOUNT)
    except keyring.errors.PasswordDeleteError:
        pass


def is_configured():
    return load() is not None
