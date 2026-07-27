-- 파생 테이블 DDL (db.reset_derived 가 실행). raw_domestic(입력)·캐시는 여기서 건드리지 않는다.
-- raw_domestic 은 api_ingest 가 수집 컬럼으로 직접 생성(db.write_raw).
DROP TABLE IF EXISTS trades;
CREATE TABLE trades (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date  TEXT,            -- ISO yyyy-mm-dd
    side        TEXT,            -- BUY | SELL
    symbol      TEXT,            -- 종목번호(해외=티커)
    name        TEXT,
    country     TEXT,            -- US | CN | KR ...
    currency    TEXT,            -- USD | KRW | CNY (native)
    quantity    REAL,
    price       REAL,            -- 거래단가 (native)
    amount      REAL,            -- 정산금액 (native, 수수료 포함)
    fee         REAL,
    fx_rate     REAL,            -- 거래시점 환율(원/통화)
    exchange    TEXT             -- 상품유형 (NASD/NYSE 등)
);

-- 현재 보유: 수량은 '유가잔고'(브로커 러닝잔량), 원가는 시간순 평균단가 엔진.
DROP TABLE IF EXISTS holdings;
CREATE TABLE holdings (
    symbol      TEXT PRIMARY KEY,
    name        TEXT,
    country     TEXT,
    currency    TEXT,
    quantity    REAL,            -- 현재 보유수량(유가잔고)
    cost_basis  REAL,            -- 보유분 원가(native)
    avg_cost    REAL             -- 평균단가(native)
);

-- 실현손익(평균단가법, 종목별 누적) + 보유기간/매매횟수
DROP TABLE IF EXISTS realized;
CREATE TABLE realized (
    symbol      TEXT PRIMARY KEY,
    name        TEXT,
    country     TEXT,
    currency    TEXT,
    sold_qty    REAL,
    proceeds    REAL,            -- 매도대금(native)
    cost        REAL,            -- 매도분 원가(native)
    pnl         REAL,            -- 실현손익(native)
    pnl_pct     REAL,
    first_buy   TEXT,            -- 최초 매수일
    last_sell   TEXT,            -- 최종 매도일
    buy_count   INTEGER,
    sell_count  INTEGER
);

-- 포지션 변동점(일별 보유 복원용). 거래일 사이는 forward-fill.
DROP TABLE IF EXISTS holdings_changes;
CREATE TABLE holdings_changes (
    date     TEXT,
    symbol   TEXT,
    quantity REAL,
    PRIMARY KEY (date, symbol)
);

-- 월말 보유수량 스냅샷 (TWR용)
DROP TABLE IF EXISTS holdings_monthly;
CREATE TABLE holdings_monthly (
    ym       TEXT,
    symbol   TEXT,
    quantity REAL,
    PRIMARY KEY (ym, symbol)
);

CREATE INDEX idx_trades_sym  ON trades(symbol);
CREATE INDEX idx_trades_date ON trades(trade_date);
CREATE INDEX idx_trades_side ON trades(side);
