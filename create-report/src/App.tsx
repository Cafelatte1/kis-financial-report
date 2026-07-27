import { useCallback, useEffect, useState, type ReactNode } from "react";
import MonthlyOverview from "./pages/MonthlyOverview";
import Overview from "./pages/Overview";
import PortfolioSection from "./pages/PortfolioSection";
import FinancialStatements from "./pages/FinancialStatements";
import PerformanceSection from "./pages/PerformanceSection";
import type { Report } from "./types";

// 상단 sticky 네비 높이(px). 섹션 래퍼의 뷰포트 높이 계산에 사용한다.
const NAV_H = 56;

function Center({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen w-full items-center justify-center bg-[#05070d] text-center text-sm text-slate-400">
      <div>{children}</div>
    </div>
  );
}

export default function App() {
  const [r, setR] = useState<Report | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [active, setActive] = useState(0);

  // 순수 뷰어: portfolio.json 만 로드해 표시한다. (데이터 생성/최신화는 `kis update`)
  const loadData = useCallback(() => {
    return fetch(`${import.meta.env.BASE_URL}data/portfolio.json`)
      .then((res) => { if (!res.ok) throw new Error(`HTTP ${res.status}`); return res.json(); })
      .then((d) => { setR(d as Report); setErr(null); })
      .catch((e) => setErr(String(e)));
  }, []);

  useEffect(() => { void loadData(); }, [loadData]);

  // 스크롤 위치에 따라 활성 탭 하이라이트(IntersectionObserver).
  useEffect(() => {
    if (!r) return;
    const els = SECTION_IDS.map((id) => document.getElementById(id)).filter(Boolean) as HTMLElement[];
    if (!els.length) return;
    const obs = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) {
            const idx = SECTION_IDS.indexOf(e.target.id);
            if (idx >= 0) setActive(idx);
          }
        }
      },
      { rootMargin: `-${NAV_H + 1}px 0px -55% 0px`, threshold: 0 },
    );
    els.forEach((el) => obs.observe(el));
    return () => obs.disconnect();
  }, [r]);

  const goTo = (idx: number) => {
    const el = document.getElementById(SECTION_IDS[idx]);
    if (el) {
      const top = el.getBoundingClientRect().top + window.scrollY - NAV_H;
      window.scrollTo({ top, behavior: "smooth" });
    }
  };

  if (err || !r) {
    return (
      <Center>
        {err
          ? <>데이터를 불러오지 못했습니다 ({err}).<br /><code>uv run kis update</code> 로 먼저 생성해 주세요.</>
          : <>불러오는 중…</>}
      </Center>
    );
  }

  return (
    <div className="min-h-screen w-full bg-[#05070d] text-slate-200">
      <Nav
        active={active}
        onTab={goTo}
        asof={r.asof.slice(0, 16).replace("T", " ")}
        ccy={r.base_ccy}
      />

      {/* 세로 스택 섹션. 각 섹션은 콘텐츠 높이로(차트는 페이지 내부에서 고정 vh 높이를
          가짐). 과거의 강제 100vh 높이를 없애 섹션 사이 빈 여백을 줄였다. */}
      <main className="mx-auto max-w-[1600px]">
        {SECTIONS.map((s) => (
          <section key={s.id} id={s.id} className="scroll-mt-14 bg-[#0b0f1a]">
            {s.render(r)}
          </section>
        ))}
      </main>
    </div>
  );
}

const SECTIONS = [
  { id: "overview", name: "요약", render: (r: Report) => <Overview r={r} /> },
  { id: "portfolio", name: "포트폴리오 분석", render: (r: Report) => <PortfolioSection r={r} /> },
  { id: "financials", name: "재무제표", render: () => <FinancialStatements /> },
  { id: "monthly", name: "월별 개요", render: (r: Report) => <MonthlyOverview r={r} /> },
  { id: "performance", name: "운용성과 분석", render: (r: Report) => <PerformanceSection r={r} /> },
];
const SECTION_IDS = SECTIONS.map((s) => s.id);

function Nav({
  active, onTab, asof, ccy,
}: {
  active: number; onTab: (i: number) => void; asof: string; ccy: string;
}) {
  return (
    <header className="sticky top-0 z-40 flex h-14 items-center justify-between border-b border-white/10 bg-[#05070d]/90 px-4 backdrop-blur sm:px-6">
      <nav className="flex items-center gap-1 overflow-x-auto">
        {SECTIONS.map((s, i) => (
          <button
            key={s.id}
            onClick={() => onTab(i)}
            className={`whitespace-nowrap rounded-full px-3 py-1.5 text-xs transition sm:text-sm ${
              active === i ? "bg-indigo-500 text-white" : "text-slate-400 hover:text-slate-200"
            }`}
          >
            {s.name}
          </button>
        ))}
      </nav>
      {(asof || ccy) && (
        <div className="hidden text-right text-[11px] leading-tight text-slate-500 md:block">
          {asof && <div>기준 {asof}</div>}
          {ccy && <div>{ccy}</div>}
        </div>
      )}
    </header>
  );
}
