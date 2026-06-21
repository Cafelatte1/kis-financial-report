# -*- mode: python ; coding: utf-8 -*-
# PyInstaller onefile 빌드. 파이프라인 스크립트는 runpy 로 동적 실행되므로
# (1) 스크립트 .py 를 datas 로 번들, (2) 그 의존성은 hiddenimports/collect_all 로 포함.
import os
from PyInstaller.utils.hooks import collect_all

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

datas = [
    (os.path.join(ROOT, "data-etl", "api_ingest.py"), "data-etl"),   # KIS OpenAPI 수집(스크랩 대체)
    (os.path.join(ROOT, "data-etl", "config.py"), "data-etl"),
    (os.path.join(ROOT, "data-etl", "db.py"), "data-etl"),
    (os.path.join(ROOT, "data-etl", "etl.py"), "data-etl"),
    (os.path.join(ROOT, "data-etl", "transform.py"), "data-etl"),
    (os.path.join(ROOT, "data-etl", "market.py"), "data-etl"),
    (os.path.join(ROOT, "data-etl", "compute.py"), "data-etl"),
    (os.path.join(ROOT, "data-etl", "schema.sql"), "data-etl"),
    (os.path.join(ROOT, "DISCLAIMER.md"), "."),
]
# create-report/dist 를 번들하되 data/(개인 금융데이터)는 제외 — 런타임엔 %APPDATA% 에서 서빙됨
_dist = os.path.join(ROOT, "create-report", "dist")
for _root, _dirs, _files in os.walk(_dist):
    rel = os.path.relpath(_root, _dist).replace("\\", "/")
    if rel == "data" or rel.startswith("data/"):
        continue
    for _f in _files:
        datas.append((os.path.join(_root, _f),
                      os.path.join("create-report/dist", "" if rel == "." else rel)))
binaries = []
hiddenimports = ["keyring.backends.Windows", "win32timezone",
                 "dotenv", "numpy", "pandas", "sqlite3", "loguru"]
# 동적 실행 스크립트의 의존성(정적분석 누락분) 강제 포함 (스크랩 폐기 → playwright 제외)
for pkg in ("requests", "yfinance", "curl_cffi"):
    try:
        d, b, h = collect_all(pkg)
        datas += d; binaries += b; hiddenimports += h
    except Exception:
        pass

a = Analysis(["app.py"], pathex=[ROOT], binaries=binaries, datas=datas,
             hiddenimports=hiddenimports, hookspath=[], excludes=["torch", "timm", "lightning"],
             noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [],
          name="KISFinancialReport",
          console=False, disable_windowed_traceback=False,
          upx=False, target_arch=None)
