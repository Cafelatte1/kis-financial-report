/** USD 풀 표기: $12,345 */
export const usd = (n: number | null | undefined) =>
  n == null ? "—" : "$" + Math.round(n).toLocaleString("en-US");

/** USD 축약: $1.2k / $3.45M */
export function usdShort(n: number | null | undefined): string {
  if (n == null) return "—";
  const a = Math.abs(n), s = n < 0 ? "-" : "";
  if (a >= 1e6) return `${s}$${(a / 1e6).toFixed(2)}M`;
  if (a >= 1e3) return `${s}$${(a / 1e3).toFixed(1)}k`;
  return `${s}$${Math.round(a)}`;
}

export const pct = (n: number | null | undefined) =>
  n == null ? "—" : `${n >= 0 ? "+" : ""}${n.toFixed(1)}%`;

export const signedShort = (n: number | null | undefined) =>
  n == null ? "—" : (n >= 0 ? "+" : "") + usdShort(n);

export const num = (n: number | null | undefined, d = 2) =>
  n == null ? "—" : n.toLocaleString("en-US", { maximumFractionDigits: d });

export const pnlColor = (n: number | null | undefined) =>
  n == null ? "text-slate-400" : n > 0 ? "text-emerald-400" : n < 0 ? "text-rose-400" : "text-slate-300";

/** 보유기간 일수 → "2.1년" / "8개월" / "12일" */
export function holdLabel(days: number | null | undefined): string {
  if (days == null) return "—";
  if (days >= 365) return `${(days / 365).toFixed(1)}년`;
  if (days >= 30) return `${Math.round(days / 30)}개월`;
  return `${days}일`;
}

export const COUNTRY_LABEL: Record<string, string> = {
  US: "🇺🇸", KR: "🇰🇷", CN: "🇨🇳", JP: "🇯🇵", HK: "🇭🇰",
};
