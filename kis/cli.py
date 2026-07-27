"""kis — KIS 포트폴리오 리포트 CLI.

  kis update [--from-date --to-date] [--mock]   # API 수집 → etl → compute
  kis serve  [--port 8777] [--no-browser]       # 대시보드 서빙(dist + /data 오버레이)
  kis status [--json]                            # 데이터 존재·신선도·보유종목 수
  kis export {report|holdings|trades|financials} # JSON 을 stdout 으로 (AI/파이프용)

데이터 위치(KIS_DATA_DIR 미설정 시 repo 로컬):
  DB   = kis/portfolio.db          (KIS_DATA_DIR 설정 시 {dir}/portfolio.db)
  JSON = create-report/public/data (KIS_DATA_DIR 설정 시 {dir}/report)
--mock 은 KIS_DATA_DIR=kis/_mock 으로 격리 실행(실제 DB 보호).
자격정보는 루트 .env (KIS_APP_KEY/KIS_SECRET_KEY/KIS_ACC — .env.example 참고).
"""
import os
import sys
import json
import sqlite3
import datetime
import argparse
import subprocess
import webbrowser
import http.server
import socketserver

HERE = os.path.dirname(os.path.abspath(__file__))      # kis/
ROOT = os.path.dirname(HERE)                            # 레포 루트
INGEST = os.path.join(HERE, "api_ingest.py")
SEED = os.path.join(HERE, "mock_seed.py")
ETL = os.path.join(HERE, "etl.py")
COMPUTE = os.path.join(HERE, "compute.py")
MOCK_DIR = os.path.join(HERE, "_mock")
DIST = os.path.join(ROOT, "create-report", "dist")      # 대시보드 정적 빌드
DASH_PORT = 8777


def _paths(env=None):
    """(db_path, report_dir) — compute.py/db.py 와 동일한 KIS_DATA_DIR 규칙."""
    d = (env or os.environ).get("KIS_DATA_DIR")
    if d:
        return os.path.join(d, "portfolio.db"), os.path.join(d, "report")
    return os.path.join(HERE, "portfolio.db"), os.path.join(ROOT, "create-report", "public", "data")


def _run(script, env, label):
    print(f"\n=== {label}: {os.path.relpath(script, ROOT)} ===", flush=True)
    r = subprocess.run([sys.executable, script], env=env, cwd=os.path.dirname(script))
    if r.returncode != 0:
        sys.exit(f"ABORTED: step '{label}' failed (exit {r.returncode})")


# ---------------------------------------------------------------- update
def cmd_update(args):
    env = dict(os.environ)
    if args.data_dir:
        env["KIS_DATA_DIR"] = os.path.abspath(args.data_dir)
    if args.mock:
        env["KIS_DATA_DIR"] = MOCK_DIR
        print(f"[MOCK] KIS_DATA_DIR = {MOCK_DIR}")
        _run(SEED, env, "1/3 mock seed")
    else:
        try:
            d1 = datetime.date.fromisoformat(args.from_date)
            d2 = datetime.date.fromisoformat(args.to_date)
        except ValueError:
            sys.exit("ABORTED: invalid date format (YYYY-MM-DD)")
        if d1 > d2:
            d1, d2 = d2, d1
        env.update(KIS_FROM_DATE=d1.isoformat(), KIS_TO_DATE=d2.isoformat())
        print(f"[REAL] period {d1} ~ {d2} | data: {env.get('KIS_DATA_DIR') or 'repo-local'}")
        _run(INGEST, env, "1/3 API ingest")            # 자격정보는 api_ingest 가 루트 .env 로드
    _run(ETL, env, "2/3 etl")
    _run(COMPUTE, env, "3/3 compute")
    db_path, report_dir = _paths(env)
    print(f"\nDONE | db: {db_path}\n     | report: {os.path.join(report_dir, 'portfolio.json')}")


# ---------------------------------------------------------------- serve
def cmd_serve(args):
    if args.data_dir:
        os.environ["KIS_DATA_DIR"] = os.path.abspath(args.data_dir)
    _, report_dir = _paths()
    if not os.path.isfile(os.path.join(DIST, "index.html")):
        sys.exit(f"ABORTED: dashboard build not found - run 'npm ci && npm run build' in create-report first ({DIST})")
    if not os.path.isfile(os.path.join(report_dir, "portfolio.json")):
        sys.exit(f"ABORTED: no report data - run 'kis update' first ({report_dir})")

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=DIST, **k)

        def translate_path(self, path):
            clean = path.split("?", 1)[0].split("#", 1)[0]
            if clean.startswith("/data/"):
                return os.path.join(report_dir, clean[len("/data/"):])
            return super().translate_path(path)

        def log_message(self, *a):
            pass

    socketserver.TCPServer.allow_reuse_address = True
    url = f"http://127.0.0.1:{args.port}/"
    with socketserver.TCPServer(("127.0.0.1", args.port), Handler) as srv:
        print(f"Dashboard: {url}  (data: {report_dir})\nCtrl+C to stop.", flush=True)
        if not args.no_browser:
            webbrowser.open(url)
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped.")


# ---------------------------------------------------------------- status
def cmd_status(args):
    if args.data_dir:
        os.environ["KIS_DATA_DIR"] = os.path.abspath(args.data_dir)
    db_path, report_dir = _paths()
    report_path = os.path.join(report_dir, "portfolio.json")
    st = {"db": db_path, "db_exists": os.path.isfile(db_path),
          "report": report_path, "report_exists": os.path.isfile(report_path),
          "asof": None, "holdings": None, "trades": None, "market_value_usd": None}
    if st["db_exists"]:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        for key, table in (("holdings", "holdings"), ("trades", "trades")):
            try:
                st[key] = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            except sqlite3.OperationalError:
                pass
        con.close()
    if st["report_exists"]:
        try:
            r = json.load(open(report_path, encoding="utf-8"))
            st["asof"] = r.get("asof")
            st["market_value_usd"] = (r.get("kpi") or {}).get("market_value")
        except (json.JSONDecodeError, OSError):
            pass
    if args.json:
        print(json.dumps(st, ensure_ascii=False, indent=2))
    else:
        print(f"db      : {st['db']} ({'OK' if st['db_exists'] else 'MISSING'})")
        print(f"report  : {st['report']} ({'OK' if st['report_exists'] else 'MISSING'})")
        print(f"asof    : {st['asof'] or '-'}")
        val = f"${st['market_value_usd']:,.0f}" if st["market_value_usd"] else "-"
        print(f"holdings: {st['holdings'] if st['holdings'] is not None else '-'} | "
              f"trades: {st['trades'] if st['trades'] is not None else '-'} | value: {val}")
    sys.exit(0 if st["db_exists"] and st["report_exists"] else 1)


# ---------------------------------------------------------------- export
def cmd_export(args):
    if args.data_dir:
        os.environ["KIS_DATA_DIR"] = os.path.abspath(args.data_dir)
    _, report_dir = _paths()
    files = {"report": "portfolio.json", "trades": "trades.json", "financials": "financials.json"}
    src = os.path.join(report_dir, files.get(args.what, "portfolio.json"))
    if not os.path.isfile(src):
        sys.exit(f"ABORTED: not found - {src} (run 'kis update' first)")
    data = json.load(open(src, encoding="utf-8"))
    if args.what == "holdings":
        data = data.get("holdings", [])
    json.dump(data, sys.stdout, ensure_ascii=False, indent=2)
    print()


def main():
    ap = argparse.ArgumentParser(prog="kis", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("update", help="KIS OpenAPI 수집 → etl → compute (전체 갱신)")
    p.add_argument("--from-date", default="2020-01-01", metavar="YYYY-MM-DD", help="조회 시작일")
    p.add_argument("--to-date", default=datetime.date.today().isoformat(), metavar="YYYY-MM-DD", help="조회 종료일")
    p.add_argument("--mock", action="store_true", help="mock 데이터로 실행(API 생략, kis/_mock 격리)")
    p.add_argument("--data-dir", help="산출물 폴더 override (기본 repo 로컬)")
    p.set_defaults(fn=cmd_update)

    p = sub.add_parser("serve", help="웹 대시보드 서빙 (create-report/dist + /data 오버레이)")
    p.add_argument("--port", type=int, default=DASH_PORT)
    p.add_argument("--no-browser", action="store_true", help="브라우저 자동 열기 생략")
    p.add_argument("--data-dir", help="report 데이터 폴더 override")
    p.set_defaults(fn=cmd_serve)

    p = sub.add_parser("status", help="데이터 존재·asof·보유종목 수 (exit 0=정상)")
    p.add_argument("--json", action="store_true", help="기계가 읽는 JSON 출력")
    p.add_argument("--data-dir", help="데이터 폴더 override")
    p.set_defaults(fn=cmd_status)

    p = sub.add_parser("export", help="리포트 JSON 을 stdout 으로 덤프")
    p.add_argument("what", choices=["report", "holdings", "trades", "financials"])
    p.add_argument("--data-dir", help="데이터 폴더 override")
    p.set_defaults(fn=cmd_export)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
