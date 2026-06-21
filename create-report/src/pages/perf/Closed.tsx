import { Card, Kpi } from "../../components/Kpi";
import { usd, usdShort, pct, holdLabel, pnlColor, COUNTRY_LABEL } from "../../lib/format";
import type { Report, ClosedPos } from "../../types";

export default function Closed({ r }: { r: Report }) {
  const c = r.closed;
  // positions 는 compute 에서 pnl 내림차순 정렬. 이익 톱10 / 손실 톱10 으로 분리(각 최대 10).
  const winners = c.positions.filter((p) => (p.pnl ?? 0) > 0).slice(0, 10);
  const losers = [...c.positions]
    .filter((p) => (p.pnl ?? 0) < 0)
    .sort((a, b) => (a.pnl ?? 0) - (b.pnl ?? 0))
    .slice(0, 10);

  return (
    <div className="flex flex-col">
      <div className="grid grid-cols-5 gap-3">
        <Kpi label="실현손익 합계" accent={pnlColor(c.total_pnl)} value={usdShort(c.total_pnl)} sub={`청산 ${c.count}종목`} />
        <Kpi label="승률" value={`${pct(c.win_rate).replace("+", "")}`} sub="이익 종목 비율" />
        <Kpi label="평균 이익" accent="text-emerald-300" value={usd(c.avg_win)} />
        <Kpi label="평균 손실" accent="text-rose-300" value={usd(c.avg_loss)} />
        <Kpi label="손익비 (Profit Factor)" accent="text-amber-300" value={`${c.profit_factor ?? "—"}`} sub="총이익 ÷ 총손실 (1↑ 흑자)" />
      </div>

      <div className="mt-3 grid grid-cols-2 gap-3">
        <PosTable title="청산 이익 상위" rows={winners} />
        <PosTable title="청산 손실 상위" rows={losers} />
      </div>
    </div>
  );
}

function PosTable({ title, rows }: { title: string; rows: ClosedPos[] }) {
  return (
    <Card>
      <div className="mb-1 text-sm font-medium text-slate-300">
        {title} <span className="text-xs text-slate-500">(상위 {rows.length})</span>
      </div>
      <table className="w-full text-[11px] tabular-nums">
        <thead>
          <tr className="text-left text-slate-500">
            <th className="py-1 font-medium">종목</th>
            <th className="py-1 text-right font-medium">실현손익</th>
            <th className="py-1 text-right font-medium">수익률</th>
            <th className="py-1 text-right font-medium">보유기간</th>
            <th className="py-1 text-right font-medium">매수/매도</th>
          </tr>
        </thead>
        <tbody>
          {rows.length ? rows.map((p) => (
            <tr key={p.symbol} className="border-t border-white/5">
              <td className="py-[5px]">
                <b className="text-slate-200">{p.symbol}</b>
                <span className="ml-1">{COUNTRY_LABEL[p.country]}</span>
                <span className="ml-1 text-slate-500">{p.name}</span>
              </td>
              <td className={`py-[5px] text-right ${pnlColor(p.pnl)}`}>{usd(p.pnl)}</td>
              <td className={`py-[5px] text-right ${pnlColor(p.pnl_pct)}`}>{pct(p.pnl_pct)}</td>
              <td className="py-[5px] text-right text-slate-300">{holdLabel(p.hold_days)}</td>
              <td className="py-[5px] text-right text-slate-500">{p.buy_count}/{p.sell_count}</td>
            </tr>
          )) : (
            <tr><td colSpan={5} className="py-3 text-center text-slate-600">없음</td></tr>
          )}
        </tbody>
      </table>
    </Card>
  );
}
