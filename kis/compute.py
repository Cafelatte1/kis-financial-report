"""portfolio.db(파생) → create-report/public/data/{portfolio,trades}.json  (기본통화 USD)

전 지표 계산을 여기서 수행한다(create-report 는 이 JSON 을 표시만).
섹션: 포트폴리오 분석(open) / 운용성과 분석(open+closed: 수익률·운용력·리스크·청산).
- 현재가·재무·일봉·벤치마크: market.py (portfolio.db 캐시)
- 일별 NAV→일별수익률→운용력/리스크, 전기간 IRR(자금가중), 청산 상세
"""
import os
import json
import math
import bisect
import datetime
import collections

import db
import market as M
import financials_api as FA

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
_DATA = os.environ.get("KIS_DATA_DIR")
# 런타임 fetch용 JSON: KIS_DATA_DIR 설정 시 {dir}/report, 아니면 create-report/public/data
OUTDIR = os.path.join(_DATA, "report") if _DATA else os.path.join(REPO, "create-report", "public", "data")

# 벤치마크: S&P500=지수(^GSPC), ACWI=ETF (MSCI ACWI 지수 무료소스 없음)
BENCH = [{"ticker": "^GSPC", "key": "SP500"}, {"ticker": "ACWI", "key": "ACWI"}]
# 스타일 프록시 ETF (닮은꼴 상관 + 누적수익 비교)
STYLES = [
    {"t": "IWF", "k": "성장"}, {"t": "IWD", "k": "가치"}, {"t": "MTUM", "k": "모멘텀"},
    {"t": "QUAL", "k": "퀄리티"}, {"t": "IWM", "k": "소형"}, {"t": "USMV", "k": "저변동"},
]
TODAY = datetime.date.today().isoformat()


def r2(x):
    return round(x, 2) if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def mean(a):
    return sum(a) / len(a) if a else 0.0


def std(a):
    if len(a) < 2:
        return 0.0
    m = mean(a)
    return math.sqrt(sum((x - m) ** 2 for x in a) / (len(a) - 1))


def xirr(flows):
    """flows=[(date_iso, amount)] → 연환산 IRR(소수). 자금가중, 과거가 불필요."""
    flows = [(datetime.date.fromisoformat(d), a) for d, a in flows if a]
    if len(flows) < 2:
        return None
    t0 = min(d for d, _ in flows)

    def npv(r):
        return sum(a / (1 + r) ** ((d - t0).days / 365.0) for d, a in flows)
    lo, hi = -0.95, 10.0
    if npv(lo) * npv(hi) > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        v = npv(mid)
        if abs(v) < 1e-4:
            return mid
        if npv(lo) * v < 0:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def main():
    con = db.connect()
    con.row_factory = db.sqlite3.Row
    holdings = [dict(r) for r in con.execute("SELECT * FROM holdings")]
    realized = [dict(r) for r in con.execute("SELECT * FROM realized")]
    trades = [dict(r) for r in con.execute("SELECT * FROM trades ORDER BY trade_date")]
    snaps = collections.defaultdict(dict)
    for r in con.execute("SELECT ym,symbol,quantity FROM holdings_monthly"):
        snaps[r["ym"]][r["symbol"]] = r["quantity"]
    changes = collections.defaultdict(list)        # symbol -> [(date, qty)]
    for r in con.execute("SELECT date,symbol,quantity FROM holdings_changes ORDER BY date"):
        changes[r["symbol"]].append((r["date"], r["quantity"]))
    rev_events = [dict(r) for r in con.execute("SELECT date,symbol,pnl,currency FROM realized_events")]
    con.close()

    usdkrw = M.get_fx("USD") or 1500.0
    # 거래시점 환율: USD/KRW 일봉 캐시(portfolio.db) → 날짜별 forward-fill 적용
    fxhist = M.get_daily_closes(["KRW=X"], start="2019-01-01")
    fxsorted = {}
    for p in ("KRW=X",):
        items = sorted(fxhist.get(p, {}).items())
        fxsorted[p] = ([d for d, _ in items], [v for _, v in items])

    def rate_asof(pair, date, fallback):
        dates, vals = fxsorted.get(pair, ([], []))
        if not dates or not date:
            return fallback
        i = bisect.bisect_right(dates, date) - 1
        return vals[i] if i >= 0 else vals[0]

    def to_usd(amt, currency, date=None):
        """native 금액 → USD. KRW는 거래시점(date) 환율로 환산(없으면 현재값)."""
        if amt is None:
            return None
        if currency == "USD":
            return amt
        if currency == "KRW":
            return amt / rate_asof("KRW=X", date, usdkrw)        # USD/KRW
        return None

    # ===== 포트폴리오 분석 (open) =====
    H = []
    for h in holdings:
        cur = h["currency"]; cost_usd = to_usd(h["cost_basis"], cur)
        row = {"symbol": h["symbol"], "name": h["name"], "country": h["country"],
               "qty": h["quantity"], "cost_basis": r2(cost_usd), "avg_cost": r2(to_usd(h["avg_cost"], cur)),
               "price": None, "value": None, "unrealized": None, "unrealized_pct": None,
               "priced": False, "beta": None, "pe": None, "pb": None, "div_yield": None, "sector": None}
        pr = M.get_price(h["symbol"], h["country"])
        if pr:
            price_usd = to_usd(pr[0], pr[1])
            if price_usd:
                val = h["quantity"] * price_usd
                row.update(price=r2(price_usd), value=r2(val), unrealized=r2(val - cost_usd),
                           unrealized_pct=r2((val - cost_usd) / cost_usd * 100) if cost_usd else None, priced=True)
        fin = M.get_financials(h["symbol"], h["country"]) or {}
        row.update(beta=fin.get("beta"), pe=fin.get("pe"), pb=fin.get("pb"),
                   div_yield=fin.get("div_yield"), sector=fin.get("sector"))
        row["fin"] = fin          # 전체 재무지표(재무 탭용)
        H.append(row)
    H.sort(key=lambda x: -(x["value"] or x["cost_basis"] or 0))

    def wavg(field):
        n = d = 0.0
        for h in H:
            if h["value"] and h.get(field) is not None:
                n += h["value"] * h[field]; d += h["value"]
        return r2(n / d) if d else None
    weighted = {k: wavg(k) for k in ("beta", "pe", "pb", "div_yield")}

    # 재무지표 전체 가중평균(평가액 가중, 값 있는 종목만)
    FIN_KEYS = ["pe", "forward_pe", "peg", "pb", "ps", "ev_ebitda", "gross_margin",
                "operating_margin", "profit_margin", "roe", "roa", "rev_growth", "eps_growth",
                "debt_to_equity", "current_ratio", "div_yield", "payout_ratio", "eps", "beta"]

    def fin_wavg(key):
        n = d = 0.0
        for h in H:
            v = (h.get("fin") or {}).get(key)
            if h["value"] and isinstance(v, (int, float)):
                n += h["value"] * v; d += h["value"]
        return r2(n / d) if d else None
    fin_weighted = {k: fin_wavg(k) for k in FIN_KEYS}

    sec = collections.defaultdict(float)
    for h in H:
        if h["value"]:
            sec[h["sector"] or "기타"] += h["value"]
    sectors = [{"key": k, "value": r2(v)} for k, v in sorted(sec.items(), key=lambda x: -x[1])]

    # ===== 청산 포지션 (closed) =====
    closed = closed_block(realized, to_usd)

    # ===== KPI =====
    invested = sum(to_usd(t["amount"], t["currency"], t["trade_date"]) or 0 for t in trades if t["side"] == "BUY")
    returned = sum(to_usd(t["amount"], t["currency"], t["trade_date"]) or 0 for t in trades if t["side"] == "SELL")
    priced = [h for h in H if h["priced"]]
    mkt = sum(h["value"] for h in priced); costp = sum(h["cost_basis"] for h in priced)
    dates = [t["trade_date"] for t in trades if t["trade_date"]]
    # 전기간 IRR(자금가중): 매수 -, 매도 +, 현재 평가액 +
    flows = [(t["trade_date"], -(to_usd(t["amount"], t["currency"], t["trade_date"]) or 0) if t["side"] == "BUY"
              else (to_usd(t["amount"], t["currency"], t["trade_date"]) or 0)) for t in trades if t["trade_date"]]
    flows.append((TODAY, mkt))
    irr = xirr(flows)
    kpi = {"invested": r2(invested), "returned": r2(returned), "realized_pnl": closed["total_pnl"],
           "market_value": r2(mkt), "unrealized": r2(mkt - costp),
           "unrealized_pct": r2((mkt - costp) / costp * 100) if costp else None,
           "irr_annual": r2(irr * 100) if irr is not None else None,
           "holdings_count": len(H), "trades_count": len(trades),
           "period": [min(dates), max(dates)] if dates else [None, None]}

    # 자금흐름 타임라인/연도별(참고)
    mflow = collections.defaultdict(lambda: [0.0, 0.0])
    for t in trades:
        if t["trade_date"]:
            mflow[t["trade_date"][:7]][0 if t["side"] == "BUY" else 1] += to_usd(t["amount"], t["currency"], t["trade_date"]) or 0
    timeline, cb, cs = [], 0.0, 0.0
    for ym in sorted(mflow):
        cb += mflow[ym][0]; cs += mflow[ym][1]
        timeline.append({"month": ym, "cum_invested": r2(cb), "cum_returned": r2(cs)})

    # ===== 종목별 기여도 (실현+미실현) =====
    contrib = {}
    for h in H:
        contrib[h["symbol"]] = {"symbol": h["symbol"], "name": h["name"],
                                "realized": 0.0, "unrealized": h["unrealized"] or 0.0,
                                "realized_pct": None, "unrealized_pct": h["unrealized_pct"]}
    for x in realized:
        c = contrib.setdefault(x["symbol"], {"symbol": x["symbol"], "name": x["name"],
                                             "realized": 0.0, "unrealized": 0.0,
                                             "realized_pct": None, "unrealized_pct": None})
        c["realized"] += to_usd(x["pnl"], x["currency"], x["last_sell"]) or 0.0
        c["realized_pct"] = x["pnl_pct"]      # 실현 수익률(원가 대비)
    contributions = sorted(
        ({"symbol": c["symbol"], "name": c["name"], "realized": r2(c["realized"]),
          "unrealized": r2(c["unrealized"]), "total": r2(c["realized"] + c["unrealized"]),
          "realized_pct": c["realized_pct"], "unrealized_pct": c["unrealized_pct"]}
         for c in contrib.values()), key=lambda x: -(x["total"] or 0))

    # ===== 섹터 틸트 (vs S&P500 근사 비중) =====
    SP500_SEC = {"Technology": 31, "Financial Services": 13, "Healthcare": 11,
                 "Consumer Cyclical": 10.5, "Communication Services": 9.5, "Industrials": 8.5,
                 "Consumer Defensive": 6, "Energy": 3.5, "Utilities": 2.5,
                 "Basic Materials": 2, "Real Estate": 2.2}
    tot = sum(h["value"] for h in priced) or 1
    psec = collections.defaultdict(float)
    for h in priced:
        psec[h["sector"] or "기타"] += h["value"]
    sector_tilt = sorted(
        ({"sector": s, "port_pct": r2(v / tot * 100), "bench_pct": SP500_SEC.get(s),
          "diff": r2(v / tot * 100 - (SP500_SEC.get(s) or 0))} for s, v in psec.items()),
        key=lambda x: -(x["port_pct"] or 0))

    # ===== 운용성과: 일별 수익률·운용력·리스크·스타일 =====
    perf = perf_block(snaps, changes, trades, to_usd)

    # ===== 월별 개요 =====
    mflow2 = collections.defaultdict(lambda: [0.0, 0.0, 0])   # ym -> [buy, sell, n]
    for t in trades:
        if t["trade_date"]:
            ym = t["trade_date"][:7]
            a = to_usd(t["amount"], t["currency"], t["trade_date"]) or 0
            mflow2[ym][0 if t["side"] == "BUY" else 1] += a
            mflow2[ym][2] += 1
    mreal = collections.defaultdict(float)
    for ev in rev_events:
        if ev["date"]:
            mreal[ev["date"][:7]] += to_usd(ev["pnl"], ev["currency"], ev["date"]) or 0

    def qty_asof(sym, ym_end):
        q = 0.0
        for dd, qq in changes.get(sym, []):
            if dd[:7] <= ym_end:
                q = qq
            else:
                break
        return q

    def prev_month(ym):
        y, mo = int(ym[:4]), int(ym[5:7]); mo -= 1
        if mo == 0:
            y -= 1; mo = 12
        return f"{y:04d}-{mo:02d}"

    nameof = {h["symbol"]: h["name"] for h in H}
    nameof.update({x["symbol"]: x["name"] for x in realized})
    monthly, prev_val = [], None
    for m in perf["returns"].get("monthly", []):
        ym = m["month"]; pm = prev_month(ym); f = mflow2.get(ym, [0, 0, 0])
        new_pos = [s for s in changes if qty_asof(s, pm) <= 1e-9 < qty_asof(s, ym)]
        closed_pos = [s for s in changes if qty_asof(s, pm) > 1e-9 >= qty_asof(s, ym)]
        monthly.append({
            "month": ym, "value": m["value"], "port_ret": m["port_ret"],
            "SP500_ret": m.get("SP500_ret"), "ACWI_ret": m.get("ACWI_ret"),
            "buy": r2(f[0]), "sell": r2(f[1]), "n_trades": f[2], "realized": r2(mreal.get(ym, 0.0)),
            "value_chg": r2(m["value"] - prev_val) if (m["value"] and prev_val) else None,
            "new": [{"symbol": s, "name": nameof.get(s, s)} for s in sorted(new_pos)],
            "closed": [{"symbol": s, "name": nameof.get(s, s)} for s in sorted(closed_pos)]})
        prev_val = m["value"]
    monthly_latest = monthly[-1] if monthly else None

    report = {"asof": datetime.datetime.now().isoformat(timespec="seconds"),
              "base_ccy": "USD", "fx": {"USDKRW": r2(usdkrw)},
              "kpi": kpi, "holdings": H, "weighted": weighted, "fin_weighted": fin_weighted, "sectors": sectors,
              "closed": closed, "timeline": timeline, "monthly": monthly, "monthly_latest": monthly_latest,
              "contributions": contributions, "sector_tilt": sector_tilt, **perf}

    # ===== 재무제표(income/balance/cashflow) — yfinance 직접 + statements 테이블 누적 =====
    # 지표(ratios)는 위 H.fin(로컬 캐시), 재무제표는 financials_api 가 기간 병합·누적 저장.
    statements = {}
    for h in H:
        st = FA.get_statements(h["symbol"], h["country"])
        if st:
            statements[h["symbol"]] = {"name": h["name"], "country": h["country"], **st}
    print(f"financials (yfinance, local merge-cache): {len(statements)}/{len(H)} holdings")

    os.makedirs(OUTDIR, exist_ok=True)
    json.dump(report, open(os.path.join(OUTDIR, "portfolio.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    json.dump(trades, open(os.path.join(OUTDIR, "trades.json"), "w", encoding="utf-8"), ensure_ascii=False)
    json.dump(statements, open(os.path.join(OUTDIR, "financials.json"), "w", encoding="utf-8"), ensure_ascii=False)

    s = perf.get("skill", {})
    print(f"export done | holdings {len(H)} closed {closed['count']} trades {len(trades)}")
    print(f"  IRR(all-period) {kpi['irr_annual']}% | mkt_value ${kpi['market_value']:,.0f} realized ${closed['total_pnl']:,.0f}")
    print(f"  skill: beta {s.get('beta')} alpha {s.get('alpha_annual')}% IR {s.get('info_ratio')} "
          f"up_capture {s.get('up_capture')}% down_capture {s.get('down_capture')}% sharpe {s.get('sharpe')}")
    print(f"  TWR {perf.get('returns',{}).get('start')}~{perf.get('returns',{}).get('end')} "
          f"coverage {perf.get('returns',{}).get('coverage')}% | weekly {len(perf.get('returns',{}).get('weekly',[]))}p")


def closed_block(realized, to_usd):
    pos = []
    for x in realized:
        if (x["sold_qty"] or 0) <= 0:
            continue
        d = x["last_sell"]
        pnl = to_usd(x["pnl"], x["currency"], d); cost = to_usd(x["cost"], x["currency"], d)
        hold = None
        if x["first_buy"] and x["last_sell"]:
            hold = (datetime.date.fromisoformat(x["last_sell"]) - datetime.date.fromisoformat(x["first_buy"])).days
        pos.append({"symbol": x["symbol"], "name": x["name"], "country": x["country"],
                    "pnl": r2(pnl), "pnl_pct": x["pnl_pct"], "proceeds": r2(to_usd(x["proceeds"], x["currency"], d)),
                    "cost": r2(cost), "first_buy": x["first_buy"], "last_sell": x["last_sell"],
                    "hold_days": hold, "buy_count": x["buy_count"], "sell_count": x["sell_count"]})
    pos.sort(key=lambda x: -(x["pnl"] or 0))
    wins = [p for p in pos if (p["pnl"] or 0) > 0]; losses = [p for p in pos if (p["pnl"] or 0) < 0]
    gross_w = sum(p["pnl"] for p in wins); gross_l = sum(p["pnl"] for p in losses)
    return {"positions": pos, "count": len(pos),
            "total_pnl": r2(sum(p["pnl"] or 0 for p in pos)),
            "win_rate": r2(len(wins) / len(pos) * 100) if pos else None,
            "avg_win": r2(gross_w / len(wins)) if wins else None,
            "avg_loss": r2(gross_l / len(losses)) if losses else None,
            "profit_factor": r2(gross_w / abs(gross_l)) if gross_l else None}


def perf_block(snaps, changes, trades, to_usd):
    try:
        return _perf(snaps, changes, trades, to_usd)
    except Exception as e:
        import traceback; traceback.print_exc()
        print("  WARNING: perf block failed (section left empty):", e)
        return {"returns": {"daily": [], "yearly": [], "start": None, "end": None, "coverage": None},
                "skill": {}, "risk": {}}


def _perf(snaps, changes, trades, to_usd):
    months = sorted(snaps)
    bench_keys = [b["key"] for b in BENCH]
    bench_tk = {b["key"]: b["ticker"] for b in BENCH}

    # 종목 → (통화·yfinance 티커) 해석. KR(00000A…) 등 비-US 도 거래소 접미사를 붙여 조회하고,
    # 종가는 거래통화(KRW 등)라 NAV 합산 전 to_usd 로 일별 환산한다(단일통화 USD NAV).
    def _ctry(cur):
        return "KR" if cur == "KRW" else "US"   # 분석대상은 KR/US(통화 KRW/USD)뿐
    sym_cur = {t["symbol"]: t["currency"] for t in trades}
    cur_of = {s: sym_cur.get(s, "USD") for d in snaps.values() for s in d}
    tk_of = {s: M.resolve_ticker(s, _ctry(cur_of[s])) for s in cur_of}

    # 0) 분할(splits) 반영 — current-share 기준 보유수량 재구성(TWR 정확도).
    #    가격은 yfinance auto_adjust(분할 소급조정) → 수량도 '현재주식수' 기준이어야 일치.
    #    qty(day) = offset + Σ(분할조정 거래수량 ≤ day),  offset = 현재잔고 − Σ(전체 분할조정 거래)
    splits_of = {s: M.get_splits(tk_of[s]) for s in cur_of}
    _sym_tr = collections.defaultdict(list)
    for t in trades:
        if t["symbol"] in cur_of and t["trade_date"]:
            _sym_tr[t["symbol"]].append((t["trade_date"], (t["quantity"] or 0.0) * (1 if t["side"] == "BUY" else -1)))
    _cur_bal = {s: (changes[s][-1][1] if changes.get(s) else 0.0) for s in cur_of}
    _adj = {}
    for s in cur_of:
        sp = splits_of.get(s) or {}
        cum, steps = 0.0, []
        for d, q in sorted(_sym_tr.get(s, [])):
            fwd = 1.0
            for sd, r in sp.items():
                if sd > d:
                    fwd *= r                        # 거래일 이후 분할비율 누적(현재주식수 환산)
            cum += q * fwd
            steps.append((d, cum))
        _adj[s] = (_cur_bal.get(s, 0.0) - cum, steps)   # offset = 잔고 − Σ조정거래

    def held_qty(sym, day):
        offset, steps = _adj.get(sym, (0.0, []))
        c = 0.0
        for d, cum in steps:
            if d <= day:
                c = cum
            else:
                break
        return offset + c

    # 월말 스냅샷을 분할조정 수량으로 재구성(원래 holdings_monthly 입력 대체)
    snaps = {ym: {s: q for s in cur_of if (q := held_qty(s, ym + "-31")) > 1e-9} for ym in months}

    # 1) 월별 커버리지로 시작월 결정(초기 소액·상폐 제외). 종가→USD 환산 후 평가.
    mcloses = M.get_monthly_closes(sorted(set(tk_of.values())) + [b["ticker"] for b in BENCH],
                                   start=months[0] + "-01")

    def _mclose_usd(s, ym):
        px = mcloses.get(tk_of[s], {}).get(ym)
        return (to_usd(px, cur_of[s], ym + "-01") or 0.0) if px else 0.0
    navm = {ym: sum(q * _mclose_usd(s, ym) for s, q in snaps[ym].items()) for ym in months}
    covm = {ym: (sum(1 for s in snaps[ym] if _mclose_usd(s, ym)) / len(snaps[ym])) if snaps[ym] else 1.0
            for ym in months}
    start = months[-1]
    for ym in reversed(months):
        if covm[ym] >= 0.85 and navm[ym] >= 2000:
            start = ym
        else:
            break
    start_date = start + "-01"

    # 2) 일봉 (윈도우 내 보유종목 티커 + 벤치마크)
    win_syms = sorted({s for ym in months if ym >= start for s in snaps[ym]})
    win_tk = sorted({tk_of[s] for s in win_syms})
    dcloses = M.get_daily_closes(
        win_tk + [b["ticker"] for b in BENCH] + ["SPY", "QQQ"] + [s["t"] for s in STYLES],
        start=start_date)

    # 거래일 = 벤치마크(^GSPC) 날짜
    days = sorted(d for d in dcloses.get("^GSPC", {}) if d >= start_date)
    # 가격 forward-fill(결측일은 직전가 사용, 티커 기준) — 데이터 공백발 NAV 점프 방지
    ff = {}
    for tk in set(win_tk) | {b["ticker"] for b in BENCH} | {"SPY", "QQQ"} | {st["t"] for st in STYLES}:
        series = dcloses.get(tk, {}); last = None; m = {}
        for day in days:
            if day in series:
                last = series[day]
            m[day] = last
        ff[tk] = m
    if not days:
        return {"returns": {"daily": [], "yearly": [], "start": start, "end": None, "coverage": None}, "skill": {}, "risk": {}}

    # 일별 현금흐름(USD)
    cf = collections.defaultdict(float)
    for t in trades:
        if t["trade_date"]:
            a = to_usd(t["amount"], t["currency"], t["trade_date"]) or 0.0
            cf[t["trade_date"]] += a if t["side"] == "BUY" else -a

    # 3) 일별 NAV·수익률 (휴장일 현금흐름은 다음 거래일로 버킷팅)
    cf_dates = sorted(cf); ci = 0
    daily, cov_ok, cov_tot = [], 0, 0
    pr_port = []; pr_b = {k: [] for k in bench_keys}
    port_cum = 100.0; bcum = {k: 100.0 for k in bench_keys}
    prev_nav = None; prev_b = {}
    for day in days:
        held = {s: held_qty(s, day) for s in win_syms}
        held = {s: q for s, q in held.items() if q > 1e-9}
        nav = sum(q * (to_usd(ff[tk_of[s]].get(day), cur_of[s], day) or 0) for s, q in held.items())
        cov_tot += len(held); cov_ok += sum(1 for s in held if ff[tk_of[s]].get(day))
        c = 0.0                                  # 직전 거래일 이후 ~ 오늘까지 모든 현금흐름 합
        while ci < len(cf_dates) and cf_dates[ci] <= day:
            c += cf[cf_dates[ci]]; ci += 1
        rec = {"date": day}
        if prev_nav and prev_nav > 0:
            rp = (nav - prev_nav - c) / prev_nav
            port_cum *= (1 + rp); pr_port.append(rp)
            for k in bench_keys:
                cb = ff[bench_tk[k]].get(day); pb = prev_b.get(k)
                rb = (cb / pb - 1) if (cb and pb) else 0.0
                bcum[k] *= (1 + rb); pr_b[k].append(rb)
        rec["port"] = r2(port_cum)
        rec["value"] = r2(nav)                 # 보유 평가액(USD) — 절대금액 토글용
        for k in bench_keys:
            rec[k] = r2(bcum[k])
        daily.append(rec)
        prev_nav = nav
        prev_b = {k: ff[bench_tk[k]].get(day) for k in bench_keys}

    coverage = r2(cov_ok / cov_tot * 100) if cov_tot else None

    # 4) 연도별 수익률(누적 인덱스 비율)
    yr = collections.defaultdict(list)
    for rec in daily:
        yr[rec["date"][:4]].append(rec)
    yearly = []
    for y in sorted(yr):
        rows = yr[y]; f, l = rows[0], rows[-1]
        def ret(k):
            return r2((l[k] / f[k] - 1) * 100) if f.get(k) and l.get(k) else None
        yearly.append({"year": y, "port": ret("port"), **{k: ret(k) for k in bench_keys}})

    # 5) 누적 곡선 주별 리샘플(smoothing) — 매 5거래일 + 마지막
    weekly = [daily[i] for i in range(0, len(daily), 5)]
    if daily and weekly[-1] is not daily[-1]:
        weekly.append(daily[-1])

    # 5b) 월별(월말) 인덱스·평가액·수익률
    bym = collections.defaultdict(list)
    for rec in daily:
        bym[rec["date"][:7]].append(rec)
    monthly_idx, prevm = [], None
    for ym in sorted(bym):
        last = bym[ym][-1]
        row = {"month": ym, "value": last.get("value"),
               "port_ret": r2((last["port"] / prevm["port"] - 1) * 100) if prevm and prevm["port"] else None}
        for k in bench_keys:
            row[k + "_ret"] = r2((last[k] / prevm[k] - 1) * 100) if prevm and prevm.get(k) else None
        monthly_idx.append(row); prevm = last

    # 6) 스타일조정 알파(보조) + 7) 스타일 닮은꼴(상관)·누적수익 비교
    style_alpha = _style_alpha(days, pr_port, ff)
    styles = _styles(days, pr_port, ff, port_cum - 100.0)

    skill = _skill(pr_port, pr_b)
    risk = _risk(daily, pr_port)
    return {"returns": {"weekly": weekly, "monthly": monthly_idx, "yearly": yearly, "start": start,
                        "end": days[-1], "coverage": coverage, "benchmarks": bench_keys},
            "skill": skill, "risk": risk, "style": style_alpha, "styles": styles}


def _corr(a, b):
    n = min(len(a), len(b))
    if n < 2:
        return None
    a, b = a[:n], b[:n]
    ma, mb = mean(a), mean(b)
    cov = sum((a[i] - ma) * (b[i] - mb) for i in range(n)) / (n - 1)
    sa, sb = std(a), std(b)
    return cov / (sa * sb) if sa and sb else None


def _styles(days, pr_port, ff, port_cum_pct):
    """각 스타일 ETF: 포폴과의 일별수익률 상관(닮은꼴) + 구간 누적수익률·포폴 초과."""
    out = []
    n = len(pr_port)
    for st in STYLES:
        s = ff.get(st["t"], {})
        sret, pret = [], []
        for i in range(1, len(days)):
            d, p = days[i], days[i - 1]
            if s.get(d) and s.get(p) and i - 1 < n:
                sret.append(s[d] / s[p] - 1); pret.append(pr_port[i - 1])
        first, last = s.get(days[0]), s.get(days[-1])
        cum = (last / first - 1) * 100 if first and last else None
        out.append({
            "key": st["k"], "ticker": st["t"],
            "corr": r2(_corr(pret, sret)) if len(sret) >= 30 else None,
            "cum_pct": r2(cum),
            "excess_pct": r2(port_cum_pct - cum) if cum is not None else None,
        })
    return out


def _style_alpha(days, pr_port, ff):
    """2팩터 회귀(시장 SPY + 성장 QQQ-SPY) → 스타일조정 알파/팩터베타."""
    try:
        import numpy as np
        spy, qqq = ff.get("SPY", {}), ff.get("QQQ", {})
        mkt, grw, port = [], [], []
        for i in range(1, len(days)):
            d, p = days[i], days[i - 1]
            if spy.get(d) and spy.get(p) and qqq.get(d) and qqq.get(p) and i - 1 < len(pr_port):
                m = spy[d] / spy[p] - 1
                g = (qqq[d] / qqq[p] - 1) - m
                mkt.append(m); grw.append(g); port.append(pr_port[i - 1])
        if len(port) < 30:
            return {}
        X = np.column_stack([np.ones(len(port)), mkt, grw])
        coef, *_ = np.linalg.lstsq(X, np.array(port), rcond=None)
        return {"adj_alpha_annual": r2(coef[0] * 252 * 100),
                "market_beta": r2(coef[1]), "growth_beta": r2(coef[2])}
    except Exception as e:
        print("  WARNING: style analysis skipped:", e)
        return {}


def _skill(port, b):
    """일별수익률 → 운용력 지표(주 벤치마크=SP500)."""
    if len(port) < 20:
        return {}
    bench = b.get("SP500", [])
    n = min(len(port), len(bench)); port, bench = port[:n], bench[:n]
    A = 252
    mp, mb = mean(port), mean(bench)
    sp, sb = std(port), std(bench)
    cov = sum((port[i] - mp) * (bench[i] - mb) for i in range(n)) / (n - 1)
    beta = cov / (sb * sb) if sb else None
    alpha = (mp - (beta or 0) * mb) * A
    diff = [port[i] - bench[i] for i in range(n)]
    te = std(diff) * math.sqrt(A)
    ir = (mean(diff) * A) / te if te else None
    up_b = [bench[i] for i in range(n) if bench[i] > 0]; up_p = [port[i] for i in range(n) if bench[i] > 0]
    dn_b = [bench[i] for i in range(n) if bench[i] < 0]; dn_p = [port[i] for i in range(n) if bench[i] < 0]
    upcap = (mean(up_p) / mean(up_b) * 100) if up_b and mean(up_b) else None
    dncap = (mean(dn_p) / mean(dn_b) * 100) if dn_b and mean(dn_b) else None
    downside = std([min(x, 0) for x in port])
    return {"beta": r2(beta), "alpha_annual": r2(alpha * 100), "corr": r2(cov / (sp * sb)) if sp and sb else None,
            "tracking_error": r2(te * 100), "info_ratio": r2(ir),
            "up_capture": r2(upcap), "down_capture": r2(dncap),
            "sharpe": r2(mp / sp * math.sqrt(A)) if sp else None,
            "sortino": r2(mp / downside * math.sqrt(A)) if downside else None,
            "win_rate": r2(sum(1 for d in diff if d > 0) / n * 100),
            "vs": "SP500"}


def _risk(daily, port_ret):
    if not daily:
        return {}
    idx = [d["port"] for d in daily if d["port"]]
    peak = idx[0]; mdd = 0.0
    for v in idx:
        peak = max(peak, v); mdd = min(mdd, v / peak - 1)
    # 최고/최악의 날
    rets = [(daily[i + 1]["date"], port_ret[i]) for i in range(len(port_ret))] if port_ret else []
    best = max(rets, key=lambda x: x[1]) if rets else (None, None)
    worst = min(rets, key=lambda x: x[1]) if rets else (None, None)
    # 월별 수익률(누적 인덱스 월말 비율)
    bym = collections.defaultdict(list)
    for d in daily:
        bym[d["date"][:7]].append(d["port"])
    months = sorted(bym); mrets = []
    for i in range(1, len(months)):
        a, b = bym[months[i - 1]][-1], bym[months[i]][-1]
        if a:
            mrets.append((months[i], (b / a - 1) * 100))
    bmonth = max(mrets, key=lambda x: x[1]) if mrets else (None, None)
    wmonth = min(mrets, key=lambda x: x[1]) if mrets else (None, None)
    # 연속 상승/하락
    up = dn = mxup = mxdn = 0
    for r in port_ret:
        if r > 0:
            up += 1; dn = 0; mxup = max(mxup, up)
        elif r < 0:
            dn += 1; up = 0; mxdn = max(mxdn, dn)
    return {"mdd": r2(mdd * 100), "vol_annual": r2(std(port_ret) * math.sqrt(252) * 100),
            "best_day": {"date": best[0], "ret": r2(best[1] * 100 if best[1] is not None else None)},
            "worst_day": {"date": worst[0], "ret": r2(worst[1] * 100 if worst[1] is not None else None)},
            "best_month": {"month": bmonth[0], "ret": r2(bmonth[1])},
            "worst_month": {"month": wmonth[0], "ret": r2(wmonth[1])},
            "max_up_streak": mxup, "max_down_streak": mxdn}


if __name__ == "__main__":
    import sys
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        import traceback
        print(f"ERROR: unexpected failure in compute: {type(e).__name__}: {e}")
        traceback.print_exc()
        sys.exit(1)
