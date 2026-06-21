import { Card, Kpi } from "../components/Kpi";
import { usd, usdShort, pct, num, pnlColor, COUNTRY_LABEL } from "../lib/format";
import type { Report } from "../types";

export default function PortfolioAnalysis({ r }: { r: Report }) {
  const k = r.kpi, w = r.weighted;
  return (
    <div className="flex flex-col">
      <div className="grid grid-cols-4 gap-3">
        <Kpi label="평가액" value={usdShort(k.market_value)} sub={`보유 ${k.holdings_count}종목`} />
        <Kpi label="미실현 손익" accent={pnlColor(k.unrealized)} value={usdShort(k.unrealized)} sub={pct(k.unrealized_pct)} />
        <Kpi label="실현 손익(누적)" accent={pnlColor(k.realized_pnl)} value={usdShort(k.realized_pnl)} />
        <Kpi label="포폴 가중 β" value={num(w.beta)} sub={`PER ${num(w.pe, 1)} · PBR ${num(w.pb, 1)}`} />
      </div>

      <div className="mt-3 flex gap-4">
        <Card className="flex-1 overflow-hidden">
          <div className="mb-1 text-sm font-medium text-slate-300">보유 종목 (평가액순)</div>
          <table className="w-full text-[12px] tabular-nums">
            <thead>
              <tr className="text-left text-slate-500">
                <th className="py-1 font-medium">종목</th>
                <th className="py-1 text-right font-medium">수량</th>
                <th className="py-1 text-right font-medium">평단</th>
                <th className="py-1 text-right font-medium">현재가</th>
                <th className="py-1 text-right font-medium">평가액</th>
                <th className="py-1 text-right font-medium">미실현</th>
                <th className="py-1 text-right font-medium">β</th>
                <th className="py-1 text-right font-medium">PER</th>
                <th className="py-1 pl-2 font-medium">섹터</th>
              </tr>
            </thead>
            <tbody>
              {r.holdings.map((h) => (
                <tr key={h.symbol} className="border-t border-white/5">
                  <td className="py-[5px]"><b className="text-slate-200">{h.symbol}</b>
                    <span className="ml-1 text-slate-500">{COUNTRY_LABEL[h.country]}</span></td>
                  <td className="py-[5px] text-right text-slate-300">{num(h.qty, 0)}</td>
                  <td className="py-[5px] text-right text-slate-400">{usd(h.avg_cost)}</td>
                  <td className="py-[5px] text-right text-slate-300">{usd(h.price)}</td>
                  <td className="py-[5px] text-right text-slate-100">{usdShort(h.value)}</td>
                  <td className={`py-[5px] text-right ${pnlColor(h.unrealized_pct)}`}>{pct(h.unrealized_pct)}</td>
                  <td className="py-[5px] text-right text-slate-400">{num(h.beta)}</td>
                  <td className="py-[5px] text-right text-slate-400">{num(h.pe, 1)}</td>
                  <td className="py-[5px] pl-2 text-slate-400">{h.sector ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>

        <div className="flex w-[27%] flex-col gap-4">
          <Card>
            <div className="mb-2 text-sm font-medium text-slate-300">포폴 가중평균</div>
            <div className="grid grid-cols-2 gap-3 text-center">
              <WStat label="베타" value={num(w.beta)} />
              <WStat label="PER" value={num(w.pe, 1)} />
              <WStat label="PBR" value={num(w.pb, 1)} />
              <WStat label="배당수익률" value={w.div_yield != null ? `${num(w.div_yield, 2)}%` : "—"} />
            </div>
          </Card>
          <Card className="flex-1">
            <div className="mb-2 text-sm font-medium text-slate-300">섹터 틸트 (포폴 vs S&P500)</div>
            <div className="space-y-2">
              {r.sector_tilt.filter((t) => t.bench_pct != null).slice(0, 7).map((t) => (
                <div key={t.sector} className="flex items-center gap-2 text-[11px]">
                  <span className="w-28 truncate text-slate-300">{t.sector}</span>
                  <span className="w-9 text-right tabular-nums text-slate-400">{num(t.port_pct, 0)}%</span>
                  <div className="relative h-3 flex-1 rounded bg-white/5">
                    <div className="absolute inset-y-0 left-0 rounded bg-indigo-400/70" style={{ width: `${Math.min(t.port_pct, 40) / 40 * 100}%` }} />
                    <div className="absolute inset-y-0 w-0.5 bg-amber-400" style={{ left: `${Math.min(t.bench_pct ?? 0, 40) / 40 * 100}%` }} />
                  </div>
                  <span className={`w-10 text-right tabular-nums ${(t.diff ?? 0) >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                    {t.diff != null ? `${t.diff >= 0 ? "+" : ""}${t.diff.toFixed(0)}` : "—"}
                  </span>
                </div>
              ))}
              <div className="pt-1 text-[10px] text-slate-500">막대=포폴 · 노란선=S&P500 · 우=초과%(+오버/−언더)</div>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}

function WStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-white/5 py-2">
      <div className="text-[11px] text-slate-500">{label}</div>
      <div className="mt-0.5 text-xl font-semibold text-slate-100 tabular-nums">{value}</div>
    </div>
  );
}
