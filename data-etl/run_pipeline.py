"""mock / 실제(KIS OpenAPI) 데이터를 분리 실행하는 파이프라인 런처.

  python data-etl/run_pipeline.py --mock   # mock 시드 → etl → compute (API 생략)
  python data-etl/run_pipeline.py --real   # KIS OpenAPI 수집 → etl → compute (실제 계좌)

모드별로 KIS_DATA_DIR 를 다르게 주입한 서브프로세스로 단계를 실행하므로
DB(portfolio.db)·산출물(report/portfolio.json)이 완전히 분리된다.
  - mock : data-etl/_mock
  - real : %APPDATA%/KIS-Report  (실제 자격정보는 keyring/.env 에서 로드해 주입)

real 은 스크랩이 아닌 KIS OpenAPI(api_ingest)로 수집한다. 코퍼레이트 액션(분할/전환/합병)은
브로커 계산값(잔고·기간손익 API)을 그대로 사용해 반영된다.
"""
import os
import sys
import argparse
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))      # data-etl/
ROOT = os.path.dirname(HERE)                            # 레포 루트
INGEST = os.path.join(HERE, "api_ingest.py")
SEED = os.path.join(HERE, "mock_seed.py")
ETL = os.path.join(HERE, "etl.py")
COMPUTE = os.path.join(HERE, "compute.py")
MOCK_DIR = os.path.join(HERE, "_mock")


def run(script, env, label):
    print(f"\n=== {label}: {os.path.relpath(script, ROOT)} ===", flush=True)
    r = subprocess.run([sys.executable, script], env=env, cwd=os.path.dirname(script))
    if r.returncode != 0:
        sys.exit(f"ABORTED: step '{label}' failed (exit {r.returncode})")


def _inject_real_credentials(env):
    """Load APP_KEY/SECRET/account from keyring (.env fallback in dev) into the subprocess env."""
    sys.path.insert(0, os.path.join(ROOT, "app"))
    import kis_config
    creds = kis_config.load()
    if not creds:
        sys.exit("ABORTED: no credentials - save APP_KEY/SECRET/account in the GUI Settings first")
    env.update(KIS_APP_KEY=creds["APP_KEY"], KIS_SECRET_KEY=creds["APP_SECRET"], KIS_ACC=creds["ACC_NUMBER"])


def main():
    ap = argparse.ArgumentParser(description="mock/real 분리 파이프라인 실행")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--mock", action="store_true", help="mock 데이터로 실행(API 생략)")
    g.add_argument("--real", action="store_true", help="실제 KIS OpenAPI 수집으로 실행")
    args = ap.parse_args()

    env = dict(os.environ)
    if args.mock:
        env["KIS_DATA_DIR"] = MOCK_DIR
        print(f"[MOCK] KIS_DATA_DIR = {MOCK_DIR}")
        run(SEED, env, "1/3 mock seed")
        run(ETL, env, "2/3 etl")
        run(COMPUTE, env, "3/3 compute")
    else:
        env.setdefault("KIS_DATA_DIR", os.path.join(os.environ.get("APPDATA", ROOT), "KIS-Report"))
        print(f"[REAL] KIS_DATA_DIR = {env['KIS_DATA_DIR']}")
        _inject_real_credentials(env)
        run(INGEST, env, "1/3 API ingest")
        run(ETL, env, "2/3 etl")
        run(COMPUTE, env, "3/3 compute")

    report = os.path.join(env["KIS_DATA_DIR"], "report", "portfolio.json")
    print(f"\nDONE | data: {env['KIS_DATA_DIR']}\n   report: {report}")


if __name__ == "__main__":
    main()
