"""재무제표(income/balance/cashflow) 수집 — yfinance 직접 + portfolio.db 누적 캐시.

yfinance 는 재무제표를
롤링 윈도우(연간 ~4년 / 분기 ~5개)로만 주고 오래된 기간은 떨구므로, 받은 기간을
statements 테이블에 **기간(period) 단위로 병합·누적**해 과거 재무제표를 보존한다.
fetched_at 이 REFRESH_DAYS(기본 7일) 이내면 캐시 그대로 반환(네트워크 0).

커버: KR/US. 그 외 국가/조회 실패는 None → 호출측(compute)에서 건너뛴다.
반환: {'annual': set|None, 'quarterly': set|None} | None,
set = {ticker, income, balance, cashflow, fetched_at}, 각 재무제표 = {기간ISO: {항목: 값}}.
"""
import os
import json
import math
import datetime

import db
import market

COVERED = {"KR", "US"}
REFRESH_DAYS = int(os.environ.get("FIN_REFRESH_DAYS", "7"))
KEYS = ("income", "balance", "cashflow")


def _normalize(df):
    """yfinance 재무제표 DataFrame → {기간(ISO): {항목: 값}}. NaN 제외."""
    if df is None or getattr(df, "empty", True):
        return {}
    out = {}
    for col in df.columns:
        try:
            period = col.strftime("%Y-%m-%d")
        except AttributeError:
            period = str(col)
        items = {}
        for item, val in df[col].items():
            if val is None or (isinstance(val, float) and math.isnan(val)):
                continue
            items[str(item)] = float(val) if isinstance(val, (int, float)) else val
        if items:
            out[period] = items
    return out


def _fetch(ticker, freq):
    """yfinance 재무제표 | None."""
    import yfinance as yf
    t = yf.Ticker(ticker)
    if freq == "quarterly":
        income, balance, cashflow = t.quarterly_financials, t.quarterly_balance_sheet, t.quarterly_cashflow
    else:
        income, balance, cashflow = t.financials, t.balance_sheet, t.cashflow
    d = {"ticker": ticker, "income": _normalize(income),
         "balance": _normalize(balance), "cashflow": _normalize(cashflow)}
    return d if (d["income"] or d["balance"] or d["cashflow"]) else None


def _merge(old, new):
    """기간 단위 병합 — 겹치는 기간은 새 값, yfinance 가 떨군 과거 기간은 보존."""
    merged = {"ticker": new.get("ticker") or (old or {}).get("ticker")}
    for k in KEYS:
        merged[k] = {**((old or {}).get(k) or {}), **(new.get(k) or {})}
    return merged


def _stale(doc):
    ts = (doc or {}).get("fetched_at")
    if not ts:
        return True
    try:
        when = datetime.datetime.fromisoformat(ts)
    except ValueError:
        return True
    return (datetime.datetime.now() - when).days >= REFRESH_DAYS


def get_statements(symbol, country):
    """{'annual': set|None, 'quarterly': set|None} | None. 캐시 신선하면 그대로, 아니면 fetch+병합."""
    if country not in COVERED:
        return None
    con = db.connect()
    out = {}
    try:
        for freq in ("annual", "quarterly"):
            row = con.execute("SELECT data FROM statements WHERE symbol=? AND freq=?",
                              (symbol, freq)).fetchone()
            doc = json.loads(row[0]) if row else None
            if _stale(doc):
                try:
                    new = _fetch(market.resolve_ticker(symbol, country), freq)
                except Exception:
                    new = None
                if new:
                    doc = _merge(doc, new)
                    doc["fetched_at"] = datetime.datetime.now().isoformat(timespec="seconds")
                    con.execute("INSERT OR REPLACE INTO statements VALUES (?,?,?,?)",
                                (symbol, freq, json.dumps(doc, ensure_ascii=False), doc["fetched_at"]))
                    con.commit()
            out[freq] = doc
    finally:
        con.close()
    return out if (out.get("annual") or out.get("quarterly")) else None
