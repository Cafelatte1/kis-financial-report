"""kis 파이프라인 분류 규칙: 거래종류·통화→국가 매핑, 분석 대상 국가.

raw_domestic(국내 전체거래내역)은 KR 주식 + 해외증권 거래 + 코퍼레이트 액션
(종목변경/분할/합병)을 모두 포함한다. DB 경로/연결은 db.py 가 단일 관리.
"""

# 국내주식 매매 거래종류 → side
KR_TRADE_TYPES = {
    "Smart+거래소주식매수": "BUY", "Smart+거래소주식매도": "SELL",
    "Smart+코스닥주식매수": "BUY", "Smart+코스닥주식매도": "SELL",
}
CURRENCY_COUNTRY = {"USD": "US", "CNY": "CN", "JPY": "JP", "HKD": "HK"}
# 분석 대상 국가. 나머지(CN/JP/HK 등)는 raw_domestic 에만 보존하고 통계에선 제외한다.
COVERED_COUNTRIES = {"KR", "US"}
