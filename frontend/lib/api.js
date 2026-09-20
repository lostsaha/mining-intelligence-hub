export const API_URL = process.env.API_URL || "http://127.0.0.1:8100";

export async function api(path, options = {}) {
  const res = await fetch(`${API_URL}${path}`, {
    cache: "no-store",
    ...options,
  });
  if (!res.ok) {
    throw new Error(`API ${path} failed: ${res.status}`);
  }
  return res.json();
}

export function formatDate(iso) {
  if (!iso) return "时间未知";
  const d = new Date(iso);
  return d.toLocaleDateString("zh-CN", { month: "long", day: "numeric" });
}

export function dayKey(iso) {
  if (!iso) return "未知日期";
  const d = new Date(iso);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  const weekdays = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];
  return `${y}-${m}-${day} ${weekdays[d.getDay()]}`;
}

export function scoreColor(score) {
  if (score >= 75) return "#c2410c";
  if (score >= 65) return "#ea580c";
  return "#9a3412";
}
