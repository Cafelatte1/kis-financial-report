"""mock 회귀 검증: KR+US 혼합이 etl→compute 에서 손계산 기대값대로 나오는지 대조.

실제 DB 보호: KIS_DATA_DIR 를 격리 폴더(data-etl/_mock)로 강제 후 임포트.
데이터·기대값은 mock_seed 에서 공유(중복 제거).

  python mock_test.py            # 검증(네트워크: compute 가 yfinance 호출)
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
os.environ["KIS_DATA_DIR"] = os.path.join(HERE, "_mock")   # ★ db/compute 임포트 전에 격리경로 고정

import db                                                  # noqa: E402
import mock_seed as MS                                     # noqa: E402


def approx(a, b, tol=0.02):
    return a is not None and abs(a - b) <= tol


def main():
    path = MS.seed()
    print(f"[mock] raw_domestic {len(MS.ROWS)}행 적재 → {path}\n")

    import etl
    etl.main()                       # 파생 생성 + 엔진수량==유가잔고 검증 출력

    print("\n========== 검증 (native 통화, etl 결과) ==========")
    con = db.connect(); con.row_factory = db.sqlite3.Row
    fails = []

    nt = con.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
    kr = con.execute("SELECT COUNT(*) FROM trades WHERE country='KR'").fetchone()[0]
    us = con.execute("SELECT COUNT(*) FROM trades WHERE country='US'").fetchone()[0]
    print(f"trades={nt} (KR {kr} / US {us})  기대 {MS.EXP_TRADES}")
    if nt != MS.EXP_TRADES:
        fails.append(f"trades {nt}≠{MS.EXP_TRADES}")

    print("\n-- 보유(holdings) --")
    hold = {r["symbol"]: r for r in con.execute("SELECT * FROM holdings")}
    for sym, (q, cost, avg, ctry, cur) in MS.EXP_HOLD.items():
        h = hold.get(sym)
        ok = h and approx(h["quantity"], q) and approx(h["cost_basis"], cost, 1) \
            and approx(h["avg_cost"], avg, 1) and h["country"] == ctry and h["currency"] == cur
        print(f"  {sym:14} qty={h and h['quantity']} cost={h and h['cost_basis']} "
              f"avg={h and h['avg_cost']} {h and h['country']}/{h and h['currency']} "
              f"기대 {q}/{cost}/{avg}/{ctry} -> {'OK' if ok else 'FAIL'}")
        if not ok:
            fails.append(f"holding {sym}")
    if len(hold) != len(MS.EXP_HOLD):
        fails.append(f"holdings 개수 {len(hold)}≠{len(MS.EXP_HOLD)}")

    print("\n-- 실현(realized) --")
    real = {r["symbol"]: r for r in con.execute("SELECT * FROM realized")}
    for sym, (sq, pnl, pct, ctry) in MS.EXP_REAL.items():
        rr = real.get(sym)
        ok = rr and approx(rr["sold_qty"], sq) and approx(rr["pnl"], pnl, 1) \
            and approx(rr["pnl_pct"], pct, 0.05) and rr["country"] == ctry
        print(f"  {sym:14} sold={rr and rr['sold_qty']} pnl={rr and rr['pnl']} "
              f"pnl%={rr and rr['pnl_pct']} {rr and rr['country']} "
              f"기대 {sq}/{pnl}/{pct}/{ctry} -> {'OK' if ok else 'FAIL'}")
        if not ok:
            fails.append(f"realized {sym}")
    con.close()

    print("\n========== compute (USD 환산 + yfinance) ==========")
    import compute
    compute.main()
    import json
    j = json.load(open(os.path.join(os.environ["KIS_DATA_DIR"], "report", "portfolio.json"), encoding="utf-8"))
    k = j["kpi"]
    countries = sorted({h["country"] for h in j["holdings"]})
    sk = j.get("skill") or {}
    print(f"\nportfolio.json: 보유 {k['holdings_count']}종목 {countries} | 청산 {j['closed']['count']} | "
          f"trades {k['trades_count']} | 평가액 ${k['market_value']} | 실현 ${k['realized_pnl']}")
    print(f"성과: TWR {j['returns']['start']}~{j['returns']['end']} 커버 {j['returns']['coverage']}% "
          f"| β {sk.get('beta')} α {sk.get('alpha_annual')}% (KR 포함 확인)")
    if k["holdings_count"] != 3:
        fails.append(f"json holdings_count {k['holdings_count']}≠3")
    if countries != ["KR", "US"]:
        fails.append(f"json 국가 {countries}≠[KR,US]")
    if j["closed"]["count"] != 4:
        fails.append(f"json closed {j['closed']['count']}≠4")
    if not sk.get("beta"):
        fails.append("성과 skill 비어있음(KR 포함 후 perf 산출 실패)")

    print("\n========== 결과 ==========")
    if fails:
        print("❌ FAIL:", fails); sys.exit(1)
    print("✅ ALL PASS — KR/US 혼합 계산 정상 (보유·실현·trades·국가분류·USD환산·청산·성과)")


if __name__ == "__main__":
    main()
