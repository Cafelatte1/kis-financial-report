"""포트폴리오 단일 DB(portfolio.db). 경로·연결·스키마의 단일 권위.

테이블 3계층:
- 입력  raw_domestic        : data-pipeline 스크랩이 직접 기록(동적 컬럼). reset 시 보존.
- 파생  trades/holdings/...  : etl.py 가 재생성. reset_derived() 가 DROP+CREATE.
- 캐시  prices/fin/hist_*    : market.py(yfinance) 가 채움. 영속(절대 드롭하지 않음).

pipeline·etl·compute·market 전부 이 모듈로 연결한다. KIS_DATA_DIR 설정 시(앱·exe)
그 폴더의 portfolio.db, 아니면 이 폴더(단독 실행).
"""
import os
import sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
_DATA = os.environ.get("KIS_DATA_DIR")
DB_PATH = os.path.join(_DATA, "portfolio.db") if _DATA else os.path.join(HERE, "portfolio.db")
_SCHEMA = os.path.join(HERE, "schema.sql")


def connect():
    """연결 + 캐시 테이블 보장(IF NOT EXISTS). 캐시는 절대 드롭하지 않는다."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    init_cache(con)
    return con


def init_cache(con):
    """yfinance 캐시 테이블(영속). 매 연결마다 호출해도 무해(IF NOT EXISTS)."""
    con.executescript("""
        CREATE TABLE IF NOT EXISTS prices(
            ticker TEXT, date TEXT, price REAL, currency TEXT, source TEXT, fetched_at TEXT,
            PRIMARY KEY(ticker, date));
        CREATE TABLE IF NOT EXISTS fin(
            ticker TEXT, date TEXT, data TEXT, fetched_at TEXT, PRIMARY KEY(ticker, date));
        CREATE TABLE IF NOT EXISTS hist_monthly(
            ticker TEXT, ym TEXT, close REAL, PRIMARY KEY(ticker, ym));
        CREATE TABLE IF NOT EXISTS hist_daily(
            ticker TEXT, date TEXT, close REAL, PRIMARY KEY(ticker, date));
        CREATE TABLE IF NOT EXISTS splits(
            ticker TEXT, date TEXT, ratio REAL, PRIMARY KEY(ticker, date));
    """)
    con.commit()


def reset_derived(con):
    """파생 테이블만 DROP+CREATE(schema.sql). raw_domestic·캐시는 건드리지 않는다."""
    with open(_SCHEMA, encoding="utf-8") as f:
        con.executescript(f.read())
    con.commit()


def write_raw(con, table, columns, rows):
    """입력 테이블(raw_domestic)을 동적 컬럼으로 재작성. rows = list[dict]."""
    cols = ", ".join(f'"{c}" TEXT' for c in columns)
    con.execute(f'DROP TABLE IF EXISTS "{table}"')
    con.execute(f'CREATE TABLE "{table}" ({cols})')
    ph = ", ".join("?" for _ in columns)
    con.executemany(f'INSERT INTO "{table}" VALUES ({ph})',
                    [[r.get(c, "") for c in columns] for r in rows])
    con.commit()


def read_rows(con, table):
    """테이블 전체를 list[dict] 로. 없으면 빈 리스트."""
    con.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in con.execute(f'SELECT * FROM "{table}"')]
    except sqlite3.OperationalError:
        return []
