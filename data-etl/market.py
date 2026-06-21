"""yfinance 단일 진입점 + 시장데이터 캐시(portfolio.db 공유).

가격/환율(prices) · 재무지표(fin) · 일·월봉(hist_daily/hist_monthly) 를 db 캐시에서
조회하고, 없으면 yfinance fetch 후 저장한다. 캐시 테이블은 db.init_cache 가 보장.

- get_price(symbol, country)        → (price_native, currency, source) | None
- get_fx(base, quote='KRW')         → 1 base = ? quote (float) | None
- get_financials(symbol, country)   → 확장 재무지표 dict | None
- get_daily_closes(tickers, start)  → {ticker: {date: close}}
- get_monthly_closes(tickers, start)→ {ticker: {ym: close}}

미지원/상장폐지 종목은 None / 빈 dict. yfinance 미지원 종목(KR/CN 등)은 prices 테이블에
직접 INSERT 해두면 그대로 사용된다.
"""
import json
import datetime

import db

# 수집 재무지표: our_key -> yfinance info key
FIN_MAP = {
    "beta": "beta", "pe": "trailingPE", "forward_pe": "forwardPE", "peg": "pegRatio",
    "pb": "priceToBook", "ps": "priceToSalesTrailing12Months", "ev_ebitda": "enterpriseToEbitda",
    "gross_margin": "grossMargins", "operating_margin": "operatingMargins", "profit_margin": "profitMargins",
    "roe": "returnOnEquity", "roa": "returnOnAssets",
    "rev_growth": "revenueGrowth", "eps_growth": "earningsGrowth",
    "debt_to_equity": "debtToEquity", "current_ratio": "currentRatio",
    "div_yield": "dividendYield", "payout_ratio": "payoutRatio",
    "market_cap": "marketCap", "eps": "trailingEps", "sector": "sector",
}
# 분수(0.xx) → 퍼센트 변환 대상 (div_yield 는 yfinance가 이미 %라 제외)
PCT100 = {"gross_margin", "operating_margin", "profit_margin", "roe", "roa",
          "rev_growth", "eps_growth", "payout_ratio"}


def to_tickers(symbol, country):
    """trades.symbol → yfinance 티커 후보(여러 거래소 시도)."""
    if country == "US":
        return [symbol.replace("/", "-")]            # BRK/B·RDS/B → BRK-B·RDS-B (yfinance 표기)
    if country == "KR":
        code = symbol[-6:]                       # 00000A002350 -> 002350
        return [f"{code}.KS", f"{code}.KQ"]
    if country == "CN":
        code = symbol.split("]")[-1].strip("[]") if "]" in symbol else symbol
        return [f"{code}.SS", f"{code}.SZ"]
    return [symbol]


def _last_price(fast_info):
    for k in ("last_price", "lastPrice", "regularMarketPrice", "previous_close"):
        try:
            v = fast_info[k]
        except (KeyError, TypeError):
            v = getattr(fast_info, k, None) if not k[0].islower() else None
        if v:
            return float(v)
    return None


def _store_price(con, ticker, date, price, currency, source):
    con.execute("INSERT OR REPLACE INTO prices VALUES (?,?,?,?,?,?)",
                (ticker, date, price, currency, source,
                 datetime.datetime.now().isoformat(timespec="seconds")))
    con.commit()


def get_price(symbol, country, date=None, fetch=True):
    """(price_native, currency, source) | None. 캐시 우선, 없으면 yfinance."""
    date = date or datetime.date.today().isoformat()
    con = db.connect()
    cands = to_tickers(symbol, country)
    for tk in cands:
        row = con.execute("SELECT price,currency,source FROM prices WHERE ticker=? AND date=?",
                          (tk, date)).fetchone()
        if row and row[0]:
            con.close()
            return row[0], row[1], row[2]
    if fetch:
        import yfinance as yf
        for tk in cands:
            try:
                fi = yf.Ticker(tk).fast_info
                price = _last_price(fi)
                cur = (fi.get("currency") if hasattr(fi, "get") else None) \
                    or {"US": "USD", "KR": "KRW", "CN": "CNY"}.get(country)
                if price and price > 0:
                    _store_price(con, tk, date, price, cur, "yfinance")
                    con.close()
                    return price, cur, "yfinance"
            except Exception:
                continue
    con.close()
    return None


def resolve_ticker(symbol, country, fetch=True):
    """symbol → 단일 yfinance 티커.

    US 는 심볼 그대로. KR/CN 등은 거래소 접미사 후보가 여러 개(.KS/.KQ ·.SS/.SZ)라
    가격·일봉 캐시에 이미 잡힌 후보를 우선 채택하고, 없으면 get_price 로 실조회해 확정한다
    (현재 보유 종목은 compute 가 앞서 get_price 를 불러 캐시가 더워진 상태).
    """
    cands = to_tickers(symbol, country)
    if len(cands) == 1:
        return cands[0]
    con = db.connect()
    try:
        for tk in cands:
            if (con.execute("SELECT 1 FROM prices WHERE ticker=? LIMIT 1", (tk,)).fetchone()
                    or con.execute("SELECT 1 FROM hist_daily WHERE ticker=? LIMIT 1", (tk,)).fetchone()):
                return tk
    finally:
        con.close()
    if fetch:
        get_price(symbol, country)                 # 작동 티커를 prices 에 캐시
        con = db.connect()
        try:
            for tk in cands:
                if con.execute("SELECT 1 FROM prices WHERE ticker=? LIMIT 1", (tk,)).fetchone():
                    return tk
        finally:
            con.close()
    return cands[0]                                 # 기본(첫 후보; KR=KOSPI .KS)


def get_fx(base, quote="KRW", date=None, fetch=True):
    """1 base = ? quote. 예: get_fx('USD') → USD/KRW. base==quote 면 1.0."""
    if base == quote:
        return 1.0
    date = date or datetime.date.today().isoformat()
    tk = f"{base}{quote}=X"
    con = db.connect()
    row = con.execute("SELECT price FROM prices WHERE ticker=? AND date=?", (tk, date)).fetchone()
    if row and row[0]:
        con.close()
        return row[0]
    if fetch:
        import yfinance as yf
        try:
            rate = _last_price(yf.Ticker(tk).fast_info)
            if rate and rate > 0:
                _store_price(con, tk, date, rate, quote, "yfinance")
                con.close()
                return rate
        except Exception:
            pass
    con.close()
    return None


def get_financials(symbol, country, date=None, fetch=True):
    """확장 재무지표 dict | None. yfinance info 다수 필드, db(fin) JSON 캐시."""
    date = date or datetime.date.today().isoformat()
    con = db.connect()
    cands = to_tickers(symbol, country)
    for tk in cands:
        row = con.execute("SELECT data FROM fin WHERE ticker=? AND date=?", (tk, date)).fetchone()
        if row:
            con.close()
            return json.loads(row[0])
    if fetch:
        import yfinance as yf
        for tk in cands:
            try:
                info = yf.Ticker(tk).info
                if not info or info.get("quoteType") is None:
                    continue
                d = {}
                for key, yf_key in FIN_MAP.items():
                    v = info.get(yf_key)
                    if isinstance(v, (int, float)) and key in PCT100:
                        v = v * 100
                    d[key] = v
                con.execute("INSERT OR REPLACE INTO fin VALUES (?,?,?,?)",
                            (tk, date, json.dumps(d), datetime.datetime.now().isoformat(timespec="seconds")))
                con.commit(); con.close()
                return d
            except Exception:
                continue
    con.close()
    return None


def get_monthly_closes(tickers, start="2019-01-01", fetch=True):
    """{ticker: {ym: close}}  월말 조정종가. 캐시 우선, 부족분만 yfinance."""
    con = db.connect()
    out, missing = {}, []
    for tk in tickers:
        rows = con.execute("SELECT ym,close FROM hist_monthly WHERE ticker=?", (tk,)).fetchall()
        if rows and min(ym for ym, _ in rows) <= start[:7]:   # 캐시가 요청범위(start)를 덮을 때만 사용
            out[tk] = {ym: c for ym, c in rows}
        else:
            missing.append(tk)
    if fetch and missing:
        import yfinance as yf
        data = yf.download(missing, start=start, interval="1mo",
                           auto_adjust=True, progress=False, group_by="ticker")
        for tk in missing:
            series = {}
            try:
                close = data[tk]["Close"] if len(missing) > 1 else data["Close"]
                for ts, v in close.items():
                    if v == v and v:                       # not NaN
                        series[ts.strftime("%Y-%m")] = float(v)
            except Exception:
                series = {}
            for ym, c in series.items():
                con.execute("INSERT OR REPLACE INTO hist_monthly VALUES (?,?,?)", (tk, ym, c))
            out[tk] = series
        con.commit()
    con.close()
    return out


def get_daily_closes(tickers, start="2022-01-01", fetch=True):
    """{ticker: {date: close}}  일별 조정종가. 캐시 우선, 부족분만 yfinance."""
    con = db.connect()
    out, missing = {}, []
    for tk in tickers:
        rows = con.execute("SELECT date,close FROM hist_daily WHERE ticker=?", (tk,)).fetchall()
        if rows and min(d for d, _ in rows)[:7] <= start[:7]:   # 캐시가 요청범위(start)를 덮을 때만 사용
            out[tk] = {d: c for d, c in rows}
        else:
            missing.append(tk)
    if fetch and missing:
        import yfinance as yf
        data = yf.download(missing, start=start, interval="1d",
                           auto_adjust=True, progress=False, group_by="ticker")
        for tk in missing:
            series = {}
            try:
                close = data[tk]["Close"] if len(missing) > 1 else data["Close"]
                for ts, v in close.items():
                    if v == v and v:
                        series[ts.strftime("%Y-%m-%d")] = float(v)
            except Exception:
                series = {}
            for d, c in series.items():
                con.execute("INSERT OR REPLACE INTO hist_daily VALUES (?,?,?)", (tk, d, c))
            out[tk] = series
        con.commit()
    con.close()
    return out


def get_splits(ticker, fetch=True):
    """{date_iso: ratio}  액면분할·무상(비율) 이벤트. yfinance Ticker.splits, db(splits) 캐시.

    분할 없는 종목도 sentinel('0000-00-00',1.0)로 '조회완료'를 표시해 재조회를 막는다.
    """
    con = db.connect()
    rows = con.execute("SELECT date,ratio FROM splits WHERE ticker=?", (ticker,)).fetchall()
    if rows:                                              # 조회 이력 있음(분할 0개여도 sentinel 존재)
        con.close()
        return {d: r for d, r in rows if r and r > 0 and d > "0001"}
    if not fetch:
        con.close()
        return {}
    out = {}
    try:
        import yfinance as yf
        s = yf.Ticker(ticker).splits
        for ts, r in s.items():
            if r and r > 0:
                out[ts.strftime("%Y-%m-%d")] = float(r)
    except Exception:
        pass
    con.execute("INSERT OR REPLACE INTO splits VALUES (?,?,?)", (ticker, "0000-00-00", 1.0))  # sentinel
    for d, r in out.items():
        con.execute("INSERT OR REPLACE INTO splits VALUES (?,?,?)", (ticker, d, r))
    con.commit()
    con.close()
    return out
