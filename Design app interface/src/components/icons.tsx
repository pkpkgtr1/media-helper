const s = { fill: "none", stroke: "currentColor", strokeWidth: 1.6, strokeLinecap: "round" as const, strokeLinejoin: "round" as const }

export const Icon = {
  library: (p: { size?: number }) => (
    <svg width={p.size ?? 18} height={p.size ?? 18} viewBox="0 0 20 20" {...s}>
      <rect x="3" y="3" width="5" height="14" rx="1" /><rect x="11" y="3" width="5" height="14" rx="1" /><path d="M5.5 6.5h.01M13.5 6.5h.01" />
    </svg>
  ),
  download: (p: { size?: number }) => (
    <svg width={p.size ?? 18} height={p.size ?? 18} viewBox="0 0 20 20" {...s}>
      <path d="M10 3v9m0 0l3.5-3.5M10 12L6.5 8.5M4 15.5h12" />
    </svg>
  ),
  settings: (p: { size?: number }) => (
    <svg width={p.size ?? 18} height={p.size ?? 18} viewBox="0 0 20 20" {...s}>
      <circle cx="10" cy="10" r="2.6" /><path d="M10 2.2v2M10 15.8v2M2.2 10h2M15.8 10h2M4.5 4.5l1.4 1.4M14.1 14.1l1.4 1.4M15.5 4.5l-1.4 1.4M5.9 14.1l-1.4 1.4" />
    </svg>
  ),
  logs: (p: { size?: number }) => (
    <svg width={p.size ?? 18} height={p.size ?? 18} viewBox="0 0 20 20" {...s}>
      <path d="M4 5h12M4 9h12M4 13h8" />
    </svg>
  ),
  folder: (p: { size?: number }) => (
    <svg width={p.size ?? 16} height={p.size ?? 16} viewBox="0 0 20 20" {...s}>
      <path d="M3 5.5A1.5 1.5 0 0 1 4.5 4h3l1.5 1.8h6A1.5 1.5 0 0 1 16.5 7.3v7.2A1.5 1.5 0 0 1 15 16H4.5A1.5 1.5 0 0 1 3 14.5z" />
    </svg>
  ),
  open: (p: { size?: number }) => (
    <svg width={p.size ?? 16} height={p.size ?? 16} viewBox="0 0 20 20" {...s}>
      <path d="M8 4H4.5A1.5 1.5 0 0 0 3 5.5v10A1.5 1.5 0 0 0 4.5 17h10a1.5 1.5 0 0 0 1.5-1.5V12M11 4h5v5M16 4l-7 7" />
    </svg>
  ),
  refresh: (p: { size?: number }) => (
    <svg width={p.size ?? 16} height={p.size ?? 16} viewBox="0 0 20 20" {...s}>
      <path d="M15.5 6.5A6 6 0 1 0 16 10M15.5 3.5v3h-3" />
    </svg>
  ),
  search: (p: { size?: number }) => (
    <svg width={p.size ?? 15} height={p.size ?? 15} viewBox="0 0 20 20" {...s}>
      <circle cx="8.5" cy="8.5" r="5" /><path d="M12.5 12.5L16 16" />
    </svg>
  ),
  image: (p: { size?: number }) => (
    <svg width={p.size ?? 16} height={p.size ?? 16} viewBox="0 0 20 20" {...s}>
      <rect x="3" y="4" width="14" height="12" rx="1.5" /><circle cx="7.5" cy="8" r="1.2" /><path d="M4 14l4-3.5 3 2.5 2.5-2L16 13.5" />
    </svg>
  ),
  close: (p: { size?: number }) => (
    <svg width={p.size ?? 16} height={p.size ?? 16} viewBox="0 0 20 20" {...s}>
      <path d="M5 5l10 10M15 5L5 15" />
    </svg>
  ),
  chevron: (p: { size?: number }) => (
    <svg width={p.size ?? 16} height={p.size ?? 16} viewBox="0 0 20 20" {...s}>
      <path d="M7 4l6 6-6 6" />
    </svg>
  ),
  retry: (p: { size?: number }) => (
    <svg width={p.size ?? 14} height={p.size ?? 14} viewBox="0 0 20 20" {...s}>
      <path d="M15.5 6.5A6 6 0 1 0 16 10M15.5 3.5v3h-3" />
    </svg>
  ),
  warn: (p: { size?: number }) => (
    <svg width={p.size ?? 16} height={p.size ?? 16} viewBox="0 0 20 20" {...s}>
      <path d="M10 3L2.5 16h15z" /><path d="M10 8v3.5M10 14h.01" />
    </svg>
  ),
  check: (p: { size?: number }) => (
    <svg width={p.size ?? 16} height={p.size ?? 16} viewBox="0 0 20 20" {...s}>
      <circle cx="10" cy="10" r="7" /><path d="M6.8 10.2l2.2 2.2 4.2-4.4" />
    </svg>
  ),
}
