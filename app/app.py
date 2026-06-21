"""KIS 포트폴리오 리포트 — 데스크톱 오케스트레이터.

켜서 [대시보드 열기] → 로컬 서버 + 브라우저로 웹 대시보드.
대시보드 안의 '재생성'(또는 GUI [재생성]) → 전체 플로우(API수집→ETL→지표계산)로 최신화.
자격정보는 OS 자격증명 저장소(DPAPI 암호화)에만 저장. DISCLAIMER.md 참조.

  python app/app.py     (개발)  /  빌드시 PyInstaller 로 exe
"""
import os
import sys
import time
import runpy
import datetime
import threading
import subprocess
import webbrowser
import http.server
import socketserver
import tkinter as tk
from tkinter import ttk, messagebox

import kis_config

APP_DIR = os.path.dirname(os.path.abspath(__file__))
FROZEN = getattr(sys, "frozen", False)
# PyInstaller 번들이면 _MEIPASS(읽기전용 코드), 아니면 레포 루트
BASE = getattr(sys, "_MEIPASS", os.path.dirname(APP_DIR))

SCRIPTS = {
    "ingest": os.path.join(BASE, "data-etl", "api_ingest.py"),   # KIS OpenAPI 수집(스크랩 대체)
    "etl": os.path.join(BASE, "data-etl", "etl.py"),
    "export": os.path.join(BASE, "data-etl", "compute.py"),
}

APP = None        # ReportApp 인스턴스(기간 선택값 제공) — scrape_env 가 참조


def data_dir():
    """모든 산출물(쓰기) 폴더. 환경변수로 하위 단계에 전달 → %APPDATA%\\KIS-Report."""
    d = os.environ.get("KIS_DATA_DIR")
    if not d:
        d = os.path.join(os.environ.get("APPDATA", APP_DIR), "KIS-Report")
        os.environ["KIS_DATA_DIR"] = d
    os.makedirs(d, exist_ok=True)
    return d


DATA_DIR = data_dir()

# ---- 로그 파일(영어): %APPDATA%\KIS-Report\logs\app.log — 10MB 로테이션(loguru) ----
# (GUI 에는 한국어 상태만 표시. 상세 진단은 이 파일에서.)
LOG_DIR = os.path.join(DATA_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "app.log")

from loguru import logger as _logger
_logger.remove()                                   # 윈도우드 exe 엔 stderr 없음 → 기본 sink 제거
_logger.add(LOG_FILE, rotation="10 MB", retention=5, encoding="utf-8",
            format="{time:YYYY-MM-DD HH:mm:ss} | {message}", level="INFO")


def applog(line):
    """English log line → rotating log file (10 MB, keep 5). Returns the line."""
    _logger.info("{}", line)                       # "{}" 로 라인의 중괄호를 그대로 보존
    return line


# ---- 대시보드(React) 로컬 서버: dist 서빙 + /data 는 쓰기폴더 오버레이 + /api 제어 ----
DIST = os.path.join(BASE, "create-report", "dist")
DATA_REPORT = os.path.join(DATA_DIR, "report")
DASH_PORT = 8777
_dash_server = None


def run_step(step, args):
    """단계 스크립트를 이 프로세스에서 __main__ 으로 실행(재진입 exe의 한 단계).

    runpy 는 스크립트 폴더를 sys.path 에 자동 추가하지 않으므로 직접 넣어준다
    (config/db/transform/market 등 상대 import 해결). 단계마다 별도 프로세스라 충돌 없음.
    """
    script = SCRIPTS[step]
    sys.path.insert(0, os.path.dirname(script))
    sys.argv = [script] + args
    runpy.run_path(script, run_name="__main__")


# ---------------------------------------------------------------- 파이프라인 러너
# 전체 플로우(스크랩→ETL→지표계산)를 백그라운드로 실행하며 상태를 추적한다.
# GUI [재생성] 과 웹 POST /api/regenerate 가 공유. 동시 실행은 1개로 가드.

def ingest_env():
    """API 수집 단계 env: 자격정보(DPAPI/keyring) + 기간(GUI의 일 단위 날짜)."""
    c = kis_config.load()
    if not c:
        raise RuntimeError("자격정보가 없습니다. [⚙ 설정]에서 APP_KEY·SECRET·계좌번호를 먼저 입력하세요.")
    frm, to = "2020-01-01", datetime.date.today().isoformat()
    if APP is not None:
        frm, to = APP.from_date.get().strip(), APP.to_date.get().strip()
    try:
        d1, d2 = datetime.date.fromisoformat(frm), datetime.date.fromisoformat(to)
    except ValueError:
        raise RuntimeError("조회 기간 형식이 잘못되었습니다 (YYYY-MM-DD).")
    if d1 > d2:
        d1, d2 = d2, d1
    env = os.environ.copy()
    env.update(KIS_APP_KEY=c["APP_KEY"], KIS_SECRET_KEY=c["APP_SECRET"], KIS_ACC=c["ACC_NUMBER"],
               KIS_FROM_DATE=d1.isoformat(), KIS_TO_DATE=d2.isoformat())
    return env


# (표시명, 단계키, env_fn?)
FULL_STEPS = [
    ("API 수집 (데이터 갱신)", "ingest", ingest_env),
    ("ETL (거래 → DB)", "etl", None),
    ("지표 계산 (대시보드 데이터)", "export", None),
]


class Runner:
    def __init__(self):
        self._lock = threading.Lock()
        self.state = "idle"          # idle | running | done | error
        self.steps = []
        self.log = []
        self.error = None

    def snapshot(self):
        return {"state": self.state, "steps": self.steps,
                "log": self.log[-60:], "error": self.error}

    def _gui(self, ko):
        """앱(GUI)에 보여줄 한국어 상태 줄."""
        self.log.append(ko)

    def _file(self, en):
        """로그 파일(%APPDATA%/.../logs)에 남길 영어 줄."""
        applog(en)

    def _logfile(self):
        return os.path.join(LOG_DIR, f"app_{time.strftime('%Y-%m-%d')}.log")

    def start(self):
        with self._lock:
            if self.state == "running":
                return False
            self.state = "running"
            self.error = None
            self.steps = [{"name": n, "status": "wait", "elapsed": None} for n, *_ in FULL_STEPS]
            self.log = []
        threading.Thread(target=self._run, daemon=True).start()
        return True

    def _run(self):
        # 재진입 실행기: exe(frozen)는 자기 자신, dev는 python+app.py 를 --run-step 으로 호출.
        # GUI 에는 한국어 단계 상태만, 상세 영어 출력은 로그 파일에만 남긴다.
        exe = sys.executable or os.path.abspath(sys.argv[0])
        self._file("=== regenerate started ===")
        for i, (name, key, *rest) in enumerate(FULL_STEPS):
            env_fn = rest[0] if rest and rest[0] else None
            self.steps[i]["status"] = "run"
            self._gui(f"▶ {name} …")
            self._file(f"--- step start: {key} ---")
            t0 = time.time()
            try:
                env = env_fn() if env_fn else os.environ.copy()
                cmd = ([exe] if FROZEN else [exe, os.path.join(APP_DIR, "app.py")]) + ["--run-step", key]
                self._file(f"$ {' '.join(cmd)}")
                p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     text=True, encoding="utf-8", errors="replace", env=env)
                for line in p.stdout:
                    self._file(line.rstrip())              # 파이프라인 출력(영어) → 로그 파일에만
                if p.wait() != 0:
                    raise RuntimeError(f"'{name}' 단계가 중단되었습니다")
                dt = round(time.time() - t0)
                self.steps[i]["status"] = "done"
                self.steps[i]["elapsed"] = dt
                self._gui(f"✅ {name} 완료 ({dt}초)")
                self._file(f"--- step done: {key} ({dt}s) ---")
            except Exception as e:
                self.steps[i]["status"] = "fail"
                self.error = str(e)
                self._gui(f"❌ {e}")
                self._gui(f"   자세한 원인은 로그를 확인하세요: {self._logfile()}")
                self._file(f"ERROR [{key}]: {e}")
                self.state = "error"
                return
        self.state = "done"
        self._gui("✅ 데이터 최신화 완료 — [대시보드 열기]로 확인하세요")
        self._file("=== regenerate done ===")


RUNNER = Runner()


class _DashHandler(http.server.SimpleHTTPRequestHandler):
    """dist 정적 서빙 + /data 는 쓰기폴더(report) 오버레이. (순수 뷰어 — 제어 API 없음)"""

    def translate_path(self, path):
        clean = path.split("?", 1)[0].split("#", 1)[0]
        if clean.startswith("/data/"):
            return os.path.join(DATA_REPORT, clean[len("/data/"):])
        return super().translate_path(path)

    def log_message(self, *a):
        pass


def ensure_dashboard_server():
    global _dash_server
    if _dash_server is None:
        socketserver.TCPServer.allow_reuse_address = True
        handler = lambda *a, **k: _DashHandler(*a, directory=DIST, **k)
        _dash_server = socketserver.TCPServer(("127.0.0.1", DASH_PORT), handler)
        threading.Thread(target=_dash_server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{DASH_PORT}/"


def stop_dashboard_server():
    """대시보드 로컬 서버 종료 → 열려있는 대시보드 페이지를 무효화(새로고침 시 끊김)."""
    global _dash_server
    if _dash_server is not None:
        try:
            _dash_server.shutdown()
            _dash_server.server_close()
        except Exception:
            pass
        _dash_server = None


class ReportApp:
    def __init__(self, root):
        global APP
        APP = self
        self.root = root
        self._log_shown = 0
        root.title("KIS 포트폴리오 리포트")
        root.geometry("760x460")
        root.configure(bg="#0b0f1a")

        top = tk.Frame(root, bg="#0b0f1a")
        top.pack(fill="x", padx=16, pady=(14, 6))
        tk.Label(top, text="📊 KIS 포트폴리오 리포트", fg="#e2e8f0", bg="#0b0f1a",
                 font=("Segoe UI", 15, "bold")).pack(side="left")
        self.btn_settings = tk.Button(top, text="⚙ 설정", command=self.configure_creds,
                                      bg="#1e293b", fg="#cbd5e1", relief="flat", padx=10)
        self.btn_settings.pack(side="right")

        # 조회 기간(일 단위, YYYY-MM-DD) — 재생성 시 KIS_FROM_DATE/KIS_TO_DATE 로 전달
        period = tk.Frame(root, bg="#0b0f1a")
        period.pack(fill="x", padx=16, pady=(2, 0))
        tk.Label(period, text="조회 기간", fg="#94a3b8", bg="#0b0f1a",
                 font=("Segoe UI", 10)).pack(side="left")
        self.from_date = tk.StringVar(value="2020-01-01")
        self.to_date = tk.StringVar(value=datetime.date.today().isoformat())
        ek = dict(bg="#1e293b", fg="#e2e8f0", relief="flat", insertbackground="#e2e8f0",
                  width=11, justify="center")
        tk.Entry(period, textvariable=self.from_date, **ek).pack(side="left", padx=(8, 2))
        tk.Label(period, text="~", fg="#94a3b8", bg="#0b0f1a").pack(side="left")
        tk.Entry(period, textvariable=self.to_date, **ek).pack(side="left", padx=(2, 0))
        tk.Label(period, text="(YYYY-MM-DD · 연 단위로 끊어 조회)", fg="#475569", bg="#0b0f1a",
                 font=("Segoe UI", 9)).pack(side="left", padx=8)

        btns = tk.Frame(root, bg="#0b0f1a")
        btns.pack(fill="x", padx=16, pady=8)
        self.btn_open = tk.Button(btns, text="🌐 대시보드 열기", command=self.open_dashboard,
                                  bg="#6366f1", fg="white", relief="flat", padx=14, pady=8,
                                  font=("Segoe UI", 10, "bold"))
        self.btn_open.pack(side="left", padx=4)
        self.btn_regen = tk.Button(btns, text="↻ 데이터 최신화", command=self.regenerate,
                                   bg="#0ea5e9", fg="white", relief="flat", padx=14, pady=8,
                                   font=("Segoe UI", 10, "bold"))
        self.btn_regen.pack(side="left", padx=4)

        self.progress = ttk.Progressbar(root, mode="indeterminate")
        self.progress.pack(fill="x", padx=16, pady=(4, 4))

        self.log_box = tk.Text(root, bg="#0f172a", fg="#cbd5e1", insertbackground="#cbd5e1",
                               font=("Consolas", 9), relief="flat", wrap="word", height=12)
        self.log_box.pack(fill="both", expand=True, padx=16, pady=(0, 14))

        if not kis_config.is_configured():
            self.log("자격정보가 없습니다. [⚙ 설정]에서 먼저 입력하세요.")
            self.root.after(400, self.configure_creds)
        else:
            self.log("준비됨. [대시보드 열기]로 보거나, [재생성]으로 최신 데이터를 만드세요.\n")
        self._poll_status()

    # ---------- UI helpers ----------
    def log(self, msg):
        self.log_box.insert("end", msg + "\n")
        self.log_box.see("end")

    def _poll_status(self):
        """러너 상태를 주기적으로 반영(웹/GUI 어느 쪽이 시작했든 진행을 보여줌)."""
        snap = RUNNER.snapshot()
        full = RUNNER.log                       # 새로 추가된 줄만 로그창에 반영
        if len(full) > self._log_shown:
            for line in full[self._log_shown:]:
                self.log("  " + line)
            self._log_shown = len(full)
        running = snap["state"] == "running"
        # 최신화 중에는 재생성·대시보드 열기·설정 모두 블록(전체 프로세스 종료까지)
        state = "disabled" if running else "normal"
        self.btn_regen.config(state=state)
        self.btn_open.config(state=state)
        self.btn_settings.config(state=state)
        if running:
            self.progress.start(12)
        else:
            self.progress.stop()
        self.root.after(600, self._poll_status)

    # ---------- actions ----------
    def regenerate(self):
        if not kis_config.is_configured():
            messagebox.showwarning("설정 필요", "먼저 [⚙ 설정]에서 자격정보를 입력하세요.")
            return
        if RUNNER.start():
            stop_dashboard_server()      # 기존 대시보드 페이지 무효화(서버 종료)
            self.log("\n=== 데이터 최신화 시작 (API수집→ETL→지표계산) ===")
            self.log("기존 대시보드는 종료됩니다. 완료 후 [대시보드 열기]로 다시 확인하세요.")
        else:
            self.log("이미 최신화가 진행 중입니다.")

    def open_dashboard(self):
        """웹 대시보드를 실제 브라우저로 연다(로컬 서버)."""
        url = ensure_dashboard_server()
        webbrowser.open(url)
        self.log(f"🌐 대시보드 열림: {url} (창을 닫아도 앱이 켜져 있으면 유지됩니다)")

    # ---------- config ----------
    def configure_creds(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("자격정보 설정")
        dlg.configure(bg="#0b0f1a")
        dlg.geometry("380x260")
        cur = kis_config.load() or {}
        tk.Label(dlg, text="계좌번호 · KIS OpenAPI 앱키 · 시크릿\n(KIS Developers 포털 발급 · OS 자격증명 저장소에 암호화 저장)",
                 fg="#94a3b8", bg="#0b0f1a", justify="left").pack(padx=16, pady=(14, 8))
        fields = {}
        for key, label, show in [("ACC_NUMBER", "계좌번호", ""),
                                 ("APP_KEY", "APP_KEY", ""),
                                 ("APP_SECRET", "APP_SECRET", "•")]:
            row = tk.Frame(dlg, bg="#0b0f1a"); row.pack(fill="x", padx=16, pady=4)
            tk.Label(row, text=label, width=12, anchor="w", fg="#cbd5e1", bg="#0b0f1a").pack(side="left")
            e = tk.Entry(row, show=show, bg="#1e293b", fg="#e2e8f0", relief="flat", insertbackground="#e2e8f0")
            e.insert(0, cur.get(key, "")); e.pack(side="left", fill="x", expand=True)
            fields[key] = e

        def save():
            v = {k: e.get().strip() for k, e in fields.items()}
            if not all(v.values()):
                messagebox.showwarning("입력 필요", "모든 항목을 입력하세요."); return
            kis_config.save(v["APP_KEY"], v["APP_SECRET"], v["ACC_NUMBER"])
            self.log("✅ 자격정보 저장됨(암호화).")
            dlg.destroy()
        tk.Button(dlg, text="저장", command=save, bg="#6366f1", fg="white", relief="flat",
                  padx=20, pady=6).pack(pady=14)


if __name__ == "__main__":
    if "--run-step" in sys.argv:
        i = sys.argv.index("--run-step")
        run_step(sys.argv[i + 1], sys.argv[i + 2:])
        sys.exit(0)
    if "--regenerate" in sys.argv:
        # 헤드리스 최신화(= GUI/웹 [데이터 최신화] 와 동일 경로). 진행 로그를 stdout 으로.
        if not kis_config.is_configured():
            print("자격정보 없음 — 먼저 GUI [⚙ 설정]에서 입력하세요.")
            sys.exit(2)
        RUNNER.start()
        shown = 0
        while True:
            while shown < len(RUNNER.log):
                print(RUNNER.log[shown]); shown += 1
            if RUNNER.state in ("done", "error"):
                break
            time.sleep(0.4)
        sys.exit(0 if RUNNER.state == "done" else 1)
    root = tk.Tk()
    ReportApp(root)
    root.mainloop()
