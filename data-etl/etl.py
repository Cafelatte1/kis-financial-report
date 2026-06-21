"""raw_* (portfolio.db) → 파생 테이블

입력 테이블 2계열(둘 중 가용한 쪽 사용):
- API 적재(api_ingest): raw_domestic(매수/매도+유가잔고) + raw_holdings + raw_realized
  → holdings/realized 는 브로커 계산값(코퍼액션 반영)을 그대로 사용.
- 스크랩/목(mock): raw_domestic 만 → 시간순 평균단가 엔진으로 holdings/realized 계산(폴백).

- trades : 매수/매도(KR 주식 + 해외증권), native 금액 — 항상 raw_domestic 에서.
- 분석 테이블은 KR/US 만 — 그 외 국가는 raw 에만 남김.
멱등(매 실행 파생 재생성). raw_*·캐시는 보존.
"""
import collections

import config as C
import db
from transform import (run_engine, current_holdings_qty, monthly_qty_snapshots,
                       position_changes, closed_periods, country_of, currency_of,
                       iso_date, TRADE_COLUMNS)


def main():
    con = db.connect()
    rows = db.read_rows(con, "raw_domestic")
    if not rows:
        raise SystemExit("ERROR: raw_domestic is empty - run data collection (api_ingest) first")
    print(f"input | raw_domestic {len(rows)} rows")

    db.reset_derived(con)                         # 파생만 재생성(raw·캐시 보존)

    # 분석 대상은 KR/US 만(나머지 국가는 raw_domestic 에만 남기고 통계에서 제외).
    raw_count = len(rows)
    rows = [r for r in rows if country_of(currency_of(r)) in C.COVERED_COUNTRIES]
    excluded = raw_count - len(rows)

    pos, realized_eng, trades, realized_events_eng = run_engine(rows)
    hold_raw = db.read_rows(con, "raw_holdings")
    real_raw = db.read_rows(con, "raw_realized")
    use_broker = bool(hold_raw or real_raw)

    # ---- trades (항상 raw_domestic 에서) ----
    con.executemany(
        f"INSERT INTO trades ({', '.join(TRADE_COLUMNS)}) "
        f"VALUES ({', '.join(':' + c for c in TRADE_COLUMNS)})", trades)

    periods = closed_periods(trades)

    # ---- holdings ----
    mismatches = []
    if use_broker:                                    # 브로커 보유(코퍼액션 반영)
        hold_rows = []
        for h in hold_raw:
            if h["country"] not in C.COVERED_COUNTRIES or float(h["quantity"] or 0) <= 1e-9:
                continue
            qty = float(h["quantity"]); cost = float(h["cost_basis"] or 0)
            hold_rows.append({
                "symbol": h["symbol"], "name": h["name"], "country": h["country"],
                "currency": h["currency"], "quantity": qty, "cost_basis": round(cost, 2),
                "avg_cost": float(h["avg_cost"]) if h["avg_cost"] else (round(cost / qty, 4) if qty else None)})
    else:                                             # 폴백: 유가잔고 + 평균단가 엔진
        cur_qty = current_holdings_qty(rows)
        hold_rows = []
        for sym, qty in cur_qty.items():
            if qty <= 1e-9:
                continue
            p = pos.get(sym, {}); eng_qty = p.get("qty", 0.0)
            if abs(eng_qty - qty) > 1e-6:
                mismatches.append((sym, round(eng_qty, 4), qty))
            cost = max(p.get("cost", 0.0), 0.0); cur = p.get("currency", "USD")
            hold_rows.append({
                "symbol": sym, "name": p.get("name"), "country": country_of(cur),
                "currency": cur, "quantity": qty, "cost_basis": round(cost, 2),
                "avg_cost": round(cost / qty, 4) if qty else None})
    con.executemany(
        "INSERT INTO holdings (symbol,name,country,currency,quantity,cost_basis,avg_cost) "
        "VALUES (:symbol,:name,:country,:currency,:quantity,:cost_basis,:avg_cost)", hold_rows)

    # ---- realized (+ 보유기간/매매횟수) / realized_events ----
    if use_broker:                                    # 브로커 실현손익(코퍼액션 반영)
        agg = collections.defaultdict(lambda: {"name": "", "currency": "", "country": "",
                                               "sold_qty": 0.0, "proceeds": 0.0, "cost": 0.0, "pnl": 0.0})
        ev_rows = []
        for r in real_raw:
            if r["country"] not in C.COVERED_COUNTRIES:
                continue
            a = agg[r["symbol"]]
            a["name"] = r["name"] or a["name"]; a["currency"] = r["currency"]; a["country"] = r["country"]
            a["sold_qty"] += float(r["sold_qty"] or 0); a["proceeds"] += float(r["proceeds"] or 0)
            a["cost"] += float(r["cost"] or 0); a["pnl"] += float(r["pnl"] or 0)
            ev_rows.append({"date": r["date"], "symbol": r["symbol"],
                            "pnl": float(r["pnl"] or 0), "currency": r["currency"]})
        rl_rows = []
        for sym, a in agg.items():
            pr = periods.get(sym, {})
            rl_rows.append({
                "symbol": sym, "name": a["name"], "country": a["country"], "currency": a["currency"],
                "sold_qty": round(a["sold_qty"], 4), "proceeds": round(a["proceeds"], 2),
                "cost": round(a["cost"], 2), "pnl": round(a["pnl"], 2),
                "pnl_pct": round(a["pnl"] / a["cost"] * 100, 2) if a["cost"] > 1e-9 else None,
                "first_buy": pr.get("first_buy"), "last_sell": pr.get("last_sell"),
                "buy_count": pr.get("buy_count"), "sell_count": pr.get("sell_count")})
    else:                                             # 폴백: 엔진 실현손익
        rl_rows = []
        for sym, rl in realized_eng.items():
            if rl["sold_qty"] <= 1e-9:
                continue
            pr = periods.get(sym, {})
            rl_rows.append({
                "symbol": sym, "name": rl["name"], "country": rl["country"], "currency": rl["currency"],
                "sold_qty": round(rl["sold_qty"], 4), "proceeds": round(rl["proceeds"], 2),
                "cost": round(rl["cost"], 2), "pnl": round(rl["pnl"], 2),
                "pnl_pct": round(rl["pnl"] / rl["cost"] * 100, 2) if rl["cost"] > 1e-9 else None,
                "first_buy": pr.get("first_buy"), "last_sell": pr.get("last_sell"),
                "buy_count": pr.get("buy_count"), "sell_count": pr.get("sell_count")})
        ev_rows = realized_events_eng
    con.executemany(
        "INSERT INTO realized (symbol,name,country,currency,sold_qty,proceeds,cost,pnl,pnl_pct,"
        "first_buy,last_sell,buy_count,sell_count) VALUES "
        "(:symbol,:name,:country,:currency,:sold_qty,:proceeds,:cost,:pnl,:pnl_pct,"
        ":first_buy,:last_sell,:buy_count,:sell_count)", rl_rows)

    # ---- holdings_changes (일별 보유 복원용) ----
    con.executemany("INSERT INTO holdings_changes (date,symbol,quantity) VALUES (?,?,?)",
                    position_changes(rows))

    # ---- realized_events (월별 실현손익용) ----
    con.execute("DROP TABLE IF EXISTS realized_events")
    con.execute("CREATE TABLE realized_events (date TEXT, symbol TEXT, pnl REAL, currency TEXT)")
    con.executemany("INSERT INTO realized_events VALUES (:date,:symbol,:pnl,:currency)", ev_rows)

    # ---- holdings_monthly (TWR용 월별 스냅샷) ----
    snaps = monthly_qty_snapshots(rows)
    snap_rows = [(ym, sym, q) for ym, d in snaps.items() for sym, q in d.items()]
    con.executemany("INSERT INTO holdings_monthly (ym,symbol,quantity) VALUES (?,?,?)", snap_rows)

    con.commit()

    # ---- summary ----
    src = "broker API (corp actions applied)" if use_broker else "avg-cost engine (fallback)"
    print(f"raw_domestic {raw_count} (excluded {excluded}, non-KR/US) | analyzed {len(rows)} | "
          f"trades {len(trades)} | holdings {len(hold_rows)} | realized {len(rl_rows)} | source: {src}")
    print("holdings (USD):")
    for h in sorted(hold_rows, key=lambda x: -(x["cost_basis"] or 0)):
        if h["currency"] == "USD":
            print(f"  {h['symbol']:6} {h['name'][:18]:18} qty={h['quantity']:>6} "
                  f"cost=${h['cost_basis']:>10,.2f} avg=${h['avg_cost']:.2f}")
    if not use_broker:
        print(f"WARNING: engine qty != balance for {len(mismatches)}: {mismatches}" if mismatches
              else "OK: engine holdings == balance (all symbols match)")
    con.close()


if __name__ == "__main__":
    import sys
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        import traceback
        print(f"ERROR: unexpected failure in etl: {type(e).__name__}: {e}")
        traceback.print_exc()
        sys.exit(1)
