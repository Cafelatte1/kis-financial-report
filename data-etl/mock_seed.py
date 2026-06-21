"""KR+US 혼합 mock 거래내역을 raw_domestic 에 적재. (run_pipeline --mock / mock_test 공용)

실제 스크랩 대신 쓰는 가짜 입력. KIS_DATA_DIR 가 가리키는 DB(portfolio.db)에 기록한다.
단독/서브프로세스 실행 시 KIS_DATA_DIR 미설정이면 data-etl/_mock 로 격리(실제 DB 보호).

  python mock_seed.py            # _mock 에 raw_domestic 적재
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault("KIS_DATA_DIR", os.path.join(HERE, "_mock"))   # 실제 DB 보호: 기본 격리

import db                                                            # noqa: E402

COLUMNS = ["계좌", "조회구간", "거래일", "거래종류", "종목번호", "종목명", "상품유형",
           "거래수량", "거래단가", "환율", "거래통화", "거래금액", "정산금액", "수수료",
           "거래세", "세금", "부가세", "유가잔고", "외화잔액", "잔액", "잔고번호", "접속매체"]

BUY_KR, SELL_KR = "Smart+거래소주식매수", "Smart+거래소주식매도"
BUY_US, SELL_US = "해외증권매수 USD", "해외증권매도 USD"


def _row(date, kind, sym, name, exch, qty, price, cur, bal, fx=""):
    amt = round(qty * price, 2)                                      # 수수료 0 가정(정산금액=거래금액)
    return {"계좌": "726********", "조회구간": f"{date[:4]}.01.01~{date[:4]}.12.31",
            "거래일": date, "거래종류": kind, "종목번호": sym, "종목명": name, "상품유형": exch,
            "거래수량": str(qty), "거래단가": str(price), "환율": fx, "거래통화": cur,
            "거래금액": str(amt), "정산금액": str(amt), "수수료": "0", "거래세": "0",
            "세금": "0", "부가세": "0", "유가잔고": str(bal), "외화잔액": "0", "잔액": "0",
            "잔고번호": "01", "접속매체": "Mock"}


ROWS = [
    # 삼성전자(KR): 10@60,000 + 10@70,000 → avg 65,000, 8주 매도 → 12주 보유
    _row("2023.01.10", BUY_KR, "00000A005930", "삼성전자", "주식", 10, 60000, "", 10),
    _row("2023.06.15", BUY_KR, "00000A005930", "삼성전자", "주식", 10, 70000, "", 20),
    _row("2024.03.20", SELL_KR, "00000A005930", "삼성전자", "주식", 8, 80000, "", 12),
    # 카카오(KR): 20@55,000 전량매도 @45,000 → 완전청산 손실
    _row("2023.02.01", BUY_KR, "00000A035720", "카카오", "주식", 20, 55000, "", 20),
    _row("2023.09.01", SELL_KR, "00000A035720", "카카오", "주식", 20, 45000, "", 0),
    # AAPL(US): 5@150 + 5@170 → avg 160, 4주 매도 → 6주 보유
    _row("2023.03.01", BUY_US, "AAPL", "애플", "NASDAQ", 5, 150, "USD", 5, "1300.00"),
    _row("2023.11.01", BUY_US, "AAPL", "애플", "NASDAQ", 5, 170, "USD", 10, "1350.00"),
    _row("2024.05.01", SELL_US, "AAPL", "애플", "NASDAQ", 4, 190, "USD", 6, "1370.00"),
    # MSFT(US): 3@280 전량매도 @400 → 완전청산 이익
    _row("2023.04.01", BUY_US, "MSFT", "마이크로소프트", "NASDAQ", 3, 280, "USD", 3, "1320.00"),
    _row("2024.01.15", SELL_US, "MSFT", "마이크로소프트", "NASDAQ", 3, 400, "USD", 0, "1310.00"),
    # NVDA(US): 10@100 매수만 → 10주 보유
    _row("2023.05.01", BUY_US, "NVDA", "엔비디아", "NASDAQ", 10, 100, "USD", 10, "1330.00"),
]

# ---- 손계산 기대값 (mock_test 검증용) ----
EXP_HOLD = {   # 종목번호 -> (qty, cost_native, avg, country, currency)
    "00000A005930": (12, 780000, 65000, "KR", "KRW"),
    "AAPL": (6, 960, 160, "US", "USD"),
    "NVDA": (10, 1000, 100, "US", "USD"),
}
EXP_REAL = {   # 종목번호 -> (sold_qty, pnl_native, pnl_pct, country)
    "00000A005930": (8, 120000, 23.08, "KR"),
    "00000A035720": (20, -200000, -18.18, "KR"),
    "AAPL": (4, 120, 18.75, "US"),
    "MSFT": (3, 360, 42.86, "US"),
}
EXP_TRADES = 11


def seed():
    """KIS_DATA_DIR 의 portfolio.db 에 raw_domestic 적재. 경로 반환."""
    con = db.connect()
    db.write_raw(con, "raw_domestic", COLUMNS, ROWS)
    con.close()
    return db.DB_PATH


if __name__ == "__main__":
    print(f"[mock_seed] raw_domestic {len(ROWS)} rows -> {seed()}")
