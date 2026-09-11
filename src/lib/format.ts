export const naira = (value: number) =>
  new Intl.NumberFormat("en-NG", {
    style: "currency",
    currency: "NGN",
    maximumFractionDigits: 0,
  }).format(value);

export const compactNaira = (value: number) => {
  if (value >= 1_000_000) return `₦${(value / 1_000_000).toFixed(1)}m`;
  if (value >= 1_000) return `₦${(value / 1_000).toFixed(0)}k`;
  return `₦${value}`;
};

export const numberFmt = (value: number) => new Intl.NumberFormat("en-NG").format(value);

export const percent = (value: number) => `${Math.round(value)}%`;

export const dateFmt = (iso: string) =>
  new Date(iso).toLocaleDateString("en-NG", { day: "numeric", month: "short", year: "numeric" });

export const dateTimeFmt = (iso: string) =>
  new Date(iso).toLocaleString("en-NG", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });

export const initials = (name: string) =>
  name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join("");

export const greeting = (d = new Date()) => {
  const h = d.getHours();
  if (h < 12) return "Good morning";
  if (h < 17) return "Good afternoon";
  return "Good evening";
};

export const titleCase = (s: string) =>
  s.replace(/[_-]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
