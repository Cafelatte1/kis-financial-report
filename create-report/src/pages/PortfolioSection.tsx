import { useState } from "react";
import { SectionTitle } from "../components/Kpi";
import PortfolioAnalysis from "./PortfolioAnalysis";
import Financials from "./Financials";
import { num } from "../lib/format";
import type { Report } from "../types";

const TABS = [
  { name: "보유 현황", el: PortfolioAnalysis },
  { name: "재무 지표", el: Financials },
];

export default function PortfolioSection({ r }: { r: Report }) {
  const [t, setT] = useState(0);
  const Panel = TABS[t].el;
  return (
    <div className="flex flex-col px-12 py-6">
      <div className="flex items-center justify-between">
        <SectionTitle title="포트폴리오 분석" />
        <div className="flex items-center gap-3">
          <span className="text-[11px] text-slate-500">USD · USDKRW {num(r.fx.USDKRW, 0)}</span>
          <div className="flex gap-1 rounded-xl bg-white/5 p-1 text-xs">
            {TABS.map((tab, i) => (
              <button key={i} onClick={() => setT(i)}
                className={`rounded-lg px-3 py-1.5 transition ${t === i ? "bg-indigo-500 text-white" : "text-slate-400 hover:text-slate-200"}`}>
                {tab.name}
              </button>
            ))}
          </div>
        </div>
      </div>
      <div className="mt-1"><Panel r={r} /></div>
    </div>
  );
}
