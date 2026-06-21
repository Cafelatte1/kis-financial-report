"""국내 전체거래내역 → 거래/보유/실현 정규화 엔진.

- 거래(trades): 매수/매도(KR 주식 + 해외증권). 금액은 native(해외=USD, KR=KRW).
- 보유(holdings): 종목별 '유가잔고'(브로커 러닝잔량, 분할·전환 이미 반영)로 현재수량 확정.
- 원가/실현: 시간순 평균단가 엔진. 액면분할(수량만), 종목변경(원가 이전), 무상입고(원가0) 처리.
"""
import datetime
import collections

import config as C


def num(s):
    if s is None:
        return None
    t = str(s).replace(",", "").replace('"', "").strip()
    if t in ("", "-"):
        return None
    try:
        return float(t)
    except ValueError:
        return None


def iso_date(s):
    if not s:
        return None
    return s.strip().replace(".", "-").replace("/", "-") or None


def classify(t):
    """거래종류 → 이벤트 종류(주식수/원가에 영향). 현금이벤트는 None."""
    t = t or ""
    if "환전" in t or "단주대금" in t:
        return None
    if "매수" in t:
        return "BUY"
    if "매도" in t:
        return "SELL"
    if "분할입고" in t:
        return "SPLIT_IN"
    if "분할출고" in t:
        return "SPLIT_OUT"
    if "배당주입고" in t or "주식지급" in t:
        return "FREE_IN"
    if "변경입고" in t:
        return "CONV_IN"
    if "변경출고" in t or "합병출고" in t:
        return "CONV_OUT"
    return None


def currency_of(r):
    return (r.get("거래통화") or "").strip() or "KRW"


def country_of(currency):
    return "KR" if currency == "KRW" else C.CURRENCY_COUNTRY.get(currency)


def amount_of(r):
    """원가/대금: 정산금액(수수료 포함) 우선, 없으면 거래금액."""
    a = num(r.get("정산금액"))
    return a if a is not None else (num(r.get("거래금액")) or 0.0)


def current_holdings_qty(rows):
    """종목별 현재 보유수량 = 주식수영향 거래 중 '최신 유가잔고'(브로커 러닝잔량)."""
    by = collections.defaultdict(list)
    for i, r in enumerate(rows):
        if classify(r.get("거래종류")):
            by[r["종목번호"]].append((r.get("거래일") or "", i, r))
    out = {}
    for sym, items in by.items():
        items.sort(key=lambda x: (x[0], x[1]))
        out[sym] = num(items[-1][2].get("유가잔고")) or 0.0
    return out


def run_engine(rows):
    """시간순 평균단가 엔진 → (positions, realized, trades).

    positions[sym] = {qty, cost, name, currency}   (원가·엔진수량)
    realized[sym]  = {pnl, proceeds, cost, sold_qty, name, currency, country}
    trades         = 매수/매도 레코드 리스트(정규화)
    """
    events, trades = [], []
    for idx, r in enumerate(rows):
        ev = classify(r.get("거래종류"))
        if ev:
            events.append((r.get("거래일") or "", idx, ev, r))
    # 같은 날: 출고(원가 빠짐) → 매매 → 입고(원가 받음) 순으로 처리(종목변경 원가이전 보장)
    prio = {"CONV_OUT": 0, "SPLIT_OUT": 0, "BUY": 1, "SELL": 1,
            "SPLIT_IN": 2, "CONV_IN": 2, "FREE_IN": 2}
    events.sort(key=lambda x: (x[0], prio.get(x[2], 1), x[1]))

    pos = collections.defaultdict(lambda: {"qty": 0.0, "cost": 0.0, "name": "", "currency": "KRW"})
    realized = collections.defaultdict(lambda: {"pnl": 0.0, "proceeds": 0.0, "cost": 0.0,
                                                "sold_qty": 0.0, "name": "", "currency": "KRW", "country": None})
    realized_events = []                       # 매도 시점별 실현손익(월별 집계용)
    pending = collections.defaultdict(float)   # 거래일 -> 종목변경 이전 원가

    for dt, idx, ev, r in events:
        sym = r["종목번호"]
        q = num(r.get("거래수량")) or 0.0
        amt = amount_of(r)
        cur = currency_of(r)
        p = pos[sym]
        p["name"] = r.get("종목명") or p["name"]
        p["currency"] = cur

        if ev == "BUY":
            p["qty"] += q; p["cost"] += amt
            trades.append(_trade(r, "BUY", cur))
        elif ev == "SELL":
            avg = p["cost"] / p["qty"] if p["qty"] > 1e-9 else 0.0
            cost_sold = avg * q
            rl = realized[sym]
            rl["pnl"] += amt - cost_sold; rl["proceeds"] += amt; rl["cost"] += cost_sold
            rl["sold_qty"] += q; rl["name"] = r.get("종목명") or rl["name"]
            rl["currency"] = cur; rl["country"] = country_of(cur)
            p["cost"] -= cost_sold; p["qty"] -= q
            realized_events.append({"date": iso_date(r.get("거래일")), "symbol": sym,
                                    "pnl": amt - cost_sold, "currency": cur})
            trades.append(_trade(r, "SELL", cur))
        elif ev == "SPLIT_IN":
            p["qty"] += q                          # 분할: 수량만, 원가 유지
        elif ev == "SPLIT_OUT":
            p["qty"] -= q
        elif ev == "FREE_IN":
            p["qty"] += q                          # 무상(배당주/지급): 원가 0
        elif ev == "CONV_OUT":
            avg = p["cost"] / p["qty"] if p["qty"] > 1e-9 else 0.0
            transferred = avg * q
            p["cost"] -= transferred; p["qty"] -= q
            pending[dt] += transferred
        elif ev == "CONV_IN":
            p["qty"] += q; p["cost"] += pending.pop(dt, 0.0)

    return pos, realized, trades, realized_events


def _trade(r, side, cur):
    return {
        "trade_date": iso_date(r.get("거래일")), "side": side,
        "symbol": r["종목번호"], "name": r.get("종목명"),
        "country": country_of(cur), "currency": cur,
        "quantity": num(r.get("거래수량")), "price": num(r.get("거래단가")),
        "amount": amount_of(r), "fee": num(r.get("수수료")),
        "fx_rate": num(r.get("환율")), "exchange": (r.get("상품유형") or "").strip() or None,
    }


TRADE_COLUMNS = ["trade_date", "side", "symbol", "name", "country", "currency",
                 "quantity", "price", "amount", "fee", "fx_rate", "exchange"]


def _months(start_ym, end_ym):
    y, m = int(start_ym[:4]), int(start_ym[5:7])
    out = []
    while f"{y:04d}-{m:02d}" <= end_ym:
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            y += 1; m = 1
    return out


def position_changes(rows):
    """포지션 변동점 [(date, symbol, qty)] — 주식수영향 거래의 유가잔고(러닝잔량).

    같은 (날짜,종목)은 마지막 값만. export 가 거래일 사이를 forward-fill 해 일별 보유 복원.
    """
    last = {}      # (date, symbol) -> (order, qty)
    for i, r in enumerate(rows):
        if classify(r.get("거래종류")):
            d = iso_date(r.get("거래일"))
            b = num(r.get("유가잔고"))
            if d:
                last[(d, r["종목번호"])] = (i, b if b is not None else 0.0)
    out = [(d, s, q) for (d, s), (_, q) in last.items()]
    out.sort(key=lambda x: (x[0], x[1]))
    return out


def closed_periods(trades):
    """종목별 보유기간/매매횟수 [(symbol, first_buy, last_sell, buy_cnt, sell_cnt)]."""
    agg = collections.defaultdict(lambda: {"buys": [], "sells": []})
    for t in trades:
        agg[t["symbol"]][("buys" if t["side"] == "BUY" else "sells")].append(t["trade_date"])
    out = {}
    for sym, d in agg.items():
        out[sym] = {
            "first_buy": min(d["buys"]) if d["buys"] else None,
            "last_sell": max(d["sells"]) if d["sells"] else None,
            "buy_count": len(d["buys"]), "sell_count": len(d["sells"])}
    return out


def monthly_qty_snapshots(rows):
    """월말 보유수량 스냅샷 {ym: {symbol: qty}} — 종목별 유가잔고(러닝잔량) 기준.

    TWR(시간가중 수익률)용. 각 월말의 보유 = 그 달 이전 마지막 주식수영향 거래의 유가잔고.
    """
    by = collections.defaultdict(list)
    for i, r in enumerate(rows):
        if classify(r.get("거래종류")):
            d = iso_date(r.get("거래일"))
            b = num(r.get("유가잔고"))
            if d:
                by[r["종목번호"]].append((d, i, b if b is not None else 0.0))
    if not by:
        return {}
    for s in by:
        by[s].sort(key=lambda x: (x[0], x[1]))
    start = min(items[0][0] for items in by.values())[:7]
    end = datetime.date.today().strftime("%Y-%m")
    snaps = {}
    for ym in _months(start, end):
        snap = {}
        for s, items in by.items():
            held = 0.0
            for d, _, b in items:
                if d[:7] <= ym:
                    held = b
                else:
                    break
            if held > 1e-9:
                snap[s] = held
        snaps[ym] = snap
    return snaps
