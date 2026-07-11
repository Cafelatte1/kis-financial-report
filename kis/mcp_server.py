"""kis-portfolio MCP 서버 (stdio) — AI 클라이언트에서 포트폴리오 데이터 조회/갱신.

실행: uv run kis-mcp  (루트 .mcp.json 이 Claude Code 에 자동 등록)
데이터: cli._paths 규칙(KIS_DATA_DIR 또는 repo 로컬)의 portfolio.db + report JSON 3종.
읽기 도구는 전부 read-only(sqlite mode=ro, JSON 파일 읽기)이며,
update_portfolio 만 파이프라인 subprocess 를 실행한다(수 분 소요).
"""
import os
import sys
import json
import sqlite3
import subprocess

from mcp.server.fastmcp import FastMCP

from cli import _paths, HERE

mcp = FastMCP("kis-portfolio")


def _report(name):
    _, report_dir = _paths()
    path = os.path.join(report_dir, name)
    if not os.path.isfile(path):
        raise ValueError(f"{name} not found ({path}) - run update_portfolio or 'kis update' first")
    return json.load(open(path, encoding="utf-8"))


def _ro_con():
    db_path, _ = _paths()
    if not os.path.isfile(db_path):
        raise ValueError(f"portfolio.db not found ({db_path}) - run update_portfolio first")
    return sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)


@mcp.tool()
def get_summary() -> dict:
    """포트폴리오 요약: 기준시각(asof), KPI(투자원금·평가액·실현/미실현손익·IRR·보유종목 수), 환율."""
    r = _report("portfolio.json")
    return {"asof": r.get("asof"), "base_ccy": r.get("base_ccy"),
            "fx": r.get("fx"), "kpi": r.get("kpi")}


@mcp.tool()
def get_holdings() -> list:
    """현재 보유종목 목록 — 수량·평단·현재가·평가액·미실현손익·베타/PER/섹터 등 재무지표 포함."""
    return _report("portfolio.json").get("holdings", [])


@mcp.tool()
def get_performance(include_series: bool = False) -> dict:
    """운용성과 — 수익률(TWR 구간·커버리지), 운용력(알파/베타/샤프/IR/포착률),
    리스크(MDD/변동성/최고·최악), 스타일조정 알파. include_series=True 면 주별 수익률 시계열 포함."""
    r = _report("portfolio.json")
    ret = dict(r.get("returns") or {})
    if not include_series:
        ret.pop("weekly", None)
    return {"returns": ret, "skill": r.get("skill"), "risk": r.get("risk"),
            "style": r.get("style"), "styles": r.get("styles"),
            "contributions": r.get("contributions")}


@mcp.tool()
def get_closed_positions() -> dict:
    """청산(전량매도) 포지션 — 종목별 실현손익·수익률·보유기간과 승률·손익비 집계."""
    return _report("portfolio.json").get("closed", {})


@mcp.tool()
def get_trades(symbol: str = "", limit: int = 100) -> list:
    """거래내역(매수/매도 체결) 조회. symbol 지정 시 해당 종목만, 최신순 limit 건."""
    con = _ro_con()
    try:
        q = "SELECT * FROM trades" + (" WHERE symbol=?" if symbol else "") + " ORDER BY trade_date DESC LIMIT ?"
        args = ([symbol, limit] if symbol else [limit])
        con.row_factory = sqlite3.Row
        return [dict(r) for r in con.execute(q, args)]
    finally:
        con.close()


@mcp.tool()
def get_financial_statements(symbol: str, freq: str = "annual") -> dict:
    """보유종목의 재무제표(손익/재무상태/현금흐름). freq: annual|quarterly. (KR/US 만 수집됨)"""
    if freq not in ("annual", "quarterly"):
        raise ValueError("freq must be 'annual' or 'quarterly'")
    fin = _report("financials.json")
    e = fin.get(symbol)
    if not e:
        raise ValueError(f"no statements for '{symbol}' (available: {', '.join(sorted(fin)) or 'none'})")
    s = e.get(freq)
    return {"symbol": symbol, "name": e.get("name"), "country": e.get("country"),
            "freq": freq, **(s or {"note": f"no {freq} data"})}


@mcp.tool()
def query_db(sql: str, limit: int = 200) -> dict:
    """portfolio.db 에 read-only SQL 실행(SELECT). 테이블: trades/holdings/realized/
    realized_events/holdings_changes/holdings_monthly + 캐시(prices/fin/hist_daily/hist_monthly/splits)
    + 원본(raw_domestic/raw_holdings/raw_realized). 결과는 limit 행까지."""
    con = _ro_con()
    try:
        cur = con.execute(sql)
        cols = [d[0] for d in cur.description] if cur.description else []
        rows = cur.fetchmany(limit)
        return {"columns": cols, "rows": [list(r) for r in rows], "truncated": len(rows) == limit}
    finally:
        con.close()


@mcp.tool()
def update_portfolio(from_date: str = "2020-01-01", to_date: str = "") -> str:
    """전체 데이터 갱신(KIS OpenAPI 수집→ETL→지표계산). 수 분 소요, KIS 토큰 발급 1회/분 제한.
    자격정보는 루트 .env 필요. 완료 후 읽기 도구들이 최신 데이터를 반환한다."""
    cmd = [sys.executable, os.path.join(HERE, "cli.py"), "update", "--from-date", from_date]
    if to_date:
        cmd += ["--to-date", to_date]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    tail = "\n".join((r.stdout or "").strip().splitlines()[-12:])
    if r.returncode != 0:
        err = "\n".join((r.stderr or "").strip().splitlines()[-6:])
        raise ValueError(f"update failed (exit {r.returncode})\n{tail}\n{err}")
    return f"update complete\n{tail}"


def main():
    mcp.run()


if __name__ == "__main__":
    main()
