"""재무제표(income/balance/cashflow) 수집 — GCP financials-backend(Cloud Run) 경유.

지표(ratios: PER·PBR·β 등)는 market.get_financials(로컬 portfolio.db 캐시)가 담당하고,
이 모듈은 '전체 재무제표'를 백엔드에서 받아온다. 백엔드는 받은 기간을 Firestore 에
기간(period) 단위로 병합·누적 저장하므로, 호출 자체가 N년치 아카이빙을 유발한다
(yfinance 가 롤링 윈도우로 떨군 과거 기간도 캐시에 보존됨).

커버: KR/US (백엔드 정책). 그 외 국가/조회 실패/네트워크 오류는 None → 호출측에서 건너뛴다.
백엔드 URL 은 비밀이 아니며 FINANCIALS_API_URL 로 override 가능.
"""
import os

import requests

BASE_URL = os.environ.get(
    "FINANCIALS_API_URL",
    "https://financials-backend-1048035848462.asia-northeast1.run.app",
).rstrip("/")
COVERED = {"KR", "US"}
_TIMEOUT = 20


def _fetch(symbol, country, freq):
    """단일 freq 재무제표 | None. {ticker,income,balance,cashflow,fetched_at}."""
    r = requests.get(f"{BASE_URL}/financials",
                     params={"symbol": symbol, "country": country, "freq": freq},
                     timeout=_TIMEOUT)
    r.raise_for_status()
    d = r.json()
    if not d.get("covered") or d.get("found") is False:
        return None
    if not (d.get("income") or d.get("balance") or d.get("cashflow")):
        return None
    return {k: d.get(k) for k in ("ticker", "income", "balance", "cashflow", "fetched_at")}


def get_statements(symbol, country):
    """{'annual': set|None, 'quarterly': set|None} | None.

    KR/US 외이거나 두 freq 모두 실패하면 None. 개별 freq 의 네트워크/HTTP 오류는 삼킨다.
    """
    if country not in COVERED:
        return None
    out = {}
    for freq in ("annual", "quarterly"):
        try:
            out[freq] = _fetch(symbol, country, freq)
        except Exception:
            out[freq] = None
    if not (out.get("annual") or out.get("quarterly")):
        return None
    return out
