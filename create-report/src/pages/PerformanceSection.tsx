import { useState } from "react";
import { SectionTitle } from "../components/Kpi";
import Returns from "./perf/Returns";
import Eval from "./perf/Eval";
import Closed from "./perf/Closed";
import type { Report } from "../types";

const TABS = [
  { name: "수익률 비교", el: Returns },
  { name: "운용력 평가", el: Eval },
  { name: "청산 포지션", el: Closed },
];

export default function PerformanceSection({ r }: { r: Report }) {
  const [t, setT] = useState(0);
  const Panel = TABS[t].el;
  return (
    <div className="flex flex-col px-12 py-6">
      <div className="flex items-center justify-between">
        <SectionTitle title="운용성과 분석" />
        <div className="flex gap-1 rounded-xl bg-white/5 p-1 text-xs">
          {TABS.map((tab, i) => (
            <button key={i} onClick={() => setT(i)}
              className={`rounded-lg px-3 py-1.5 transition ${t === i ? "bg-indigo-500 text-white" : "text-slate-400 hover:text-slate-200"}`}>
              {tab.name}
            </button>
          ))}
        </div>
      </div>
      <div className="mt-1"><Panel r={r} /></div>
    </div>
  );
}
