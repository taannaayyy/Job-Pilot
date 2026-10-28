const dateFmt = new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short" });
const dateTimeFmt = new Intl.DateTimeFormat(undefined, {
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

export const fmtDate = (iso: string | null) => (iso ? dateFmt.format(new Date(iso)) : "—");
export const fmtDateTime = (iso: string) => dateTimeFmt.format(new Date(iso));

/** "today", "yesterday", "5 days ago", "3 weeks ago", or the date for older ones. */
export function fmtAgo(iso: string): string {
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000);
  if (days <= 0) return "today";
  if (days === 1) return "yesterday";
  if (days < 14) return `${days} days ago`;
  if (days < 60) return `${Math.floor(days / 7)} weeks ago`;
  return fmtDate(iso);
}

export const daysSince = (iso: string) => (Date.now() - new Date(iso).getTime()) / 86_400_000;
