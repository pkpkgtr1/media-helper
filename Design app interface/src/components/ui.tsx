import type { ReactNode } from "react"
import type { FileState } from "../data"

type BtnVariant = "primary" | "default" | "ghost" | "danger"

export function Button({
  children,
  variant = "default",
  size = "md",
  disabled,
  title,
  onClick,
  className = "",
}: {
  children: ReactNode
  variant?: BtnVariant
  size?: "sm" | "md"
  disabled?: boolean
  title?: string
  onClick?: () => void
  className?: string
}) {
  const base =
    "inline-flex items-center justify-center gap-1.5 rounded-[6px] font-medium whitespace-nowrap transition-colors duration-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50 disabled:opacity-45 disabled:cursor-not-allowed select-none"
  const sizes = {
    sm: "h-7 px-2.5 text-[12px]",
    md: "h-8 px-3 text-[13px]",
  }
  const variants: Record<BtnVariant, string> = {
    primary:
      "bg-primary text-primary-foreground hover:bg-primary-hover border border-transparent",
    default:
      "bg-card text-secondary-foreground border border-border-strong hover:bg-secondary",
    ghost: "text-secondary-foreground hover:bg-secondary border border-transparent",
    danger:
      "bg-card text-[color:var(--status-failed)] border border-border-strong hover:bg-[color:var(--status-failed-bg)]",
  }
  return (
    <button
      title={title}
      disabled={disabled}
      onClick={onClick}
      className={`${base} ${sizes[size]} ${variants[variant]} ${className}`}
    >
      {children}
    </button>
  )
}

export function IconButton({
  children,
  title,
  onClick,
  active,
}: {
  children: ReactNode
  title?: string
  onClick?: () => void
  active?: boolean
}) {
  return (
    <button
      title={title}
      onClick={onClick}
      className={`inline-flex h-8 w-8 items-center justify-center rounded-[6px] border border-transparent text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50 ${
        active ? "bg-secondary text-foreground" : ""
      }`}
    >
      {children}
    </button>
  )
}

export function Field({
  label,
  children,
  width,
}: {
  label: string
  children: ReactNode
  width?: string
}) {
  return (
    <label className="flex flex-col gap-1" style={{ width }}>
      <span className="text-[11px] font-medium text-muted-foreground">{label}</span>
      {children}
    </label>
  )
}

const inputCls =
  "h-8 rounded-[6px] border border-border-strong bg-card px-2.5 text-[13px] text-foreground transition-colors placeholder:text-muted-foreground focus:border-ring focus:outline-none focus:ring-2 focus:ring-ring/25"

export function TextInput(props: {
  value?: string
  placeholder?: string
  onChange?: (v: string) => void
  onEnter?: () => void
  className?: string
  mono?: boolean
}) {
  return (
    <input
      value={props.value}
      placeholder={props.placeholder}
      onChange={(e) => props.onChange?.(e.target.value)}
      onKeyDown={(e) => {
        if (e.key === "Enter") {
          e.preventDefault()
          props.onEnter?.()
        }
      }}
      className={`${inputCls} ${props.mono ? "font-mono" : ""} ${props.className ?? ""}`}
    />
  )
}

export function Select({
  value,
  options,
  onChange,
  className = "",
}: {
  value: string
  options: string[]
  onChange?: (v: string) => void
  className?: string
}) {
  return (
    <div className={`relative ${className}`}>
      <select
        value={value}
        onChange={(e) => onChange?.(e.target.value)}
        className={`${inputCls} w-full appearance-none pr-7 cursor-pointer`}
      >
        {options.map((o) => (
          <option key={o}>{o}</option>
        ))}
      </select>
      <svg
        className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground"
        width="12" height="12" viewBox="0 0 12 12" fill="none"
      >
        <path d="M2.5 4.5L6 8l3.5-3.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </div>
  )
}

export function Checkbox({
  checked,
  indeterminate,
  onChange,
}: {
  checked: boolean
  indeterminate?: boolean
  onChange?: (v: boolean) => void
}) {
  return (
    <button
      role="checkbox"
      aria-checked={indeterminate ? "mixed" : checked}
      onClick={() => onChange?.(!checked)}
      className={`flex h-[16px] w-[16px] shrink-0 items-center justify-center rounded-[4px] border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50 ${
        checked || indeterminate
          ? "border-primary bg-primary text-primary-foreground"
          : "border-border-strong bg-card hover:border-muted-foreground"
      }`}
    >
      {indeterminate ? (
        <span className="h-[2px] w-[8px] rounded bg-current" />
      ) : checked ? (
        <svg width="11" height="11" viewBox="0 0 12 12" fill="none">
          <path d="M2.5 6.2l2.2 2.2L9.5 3.6" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      ) : null}
    </button>
  )
}

export function Toggle({
  checked,
  onChange,
}: {
  checked: boolean
  onChange?: (v: boolean) => void
}) {
  return (
    <button
      role="switch"
      aria-checked={checked}
      onClick={() => onChange?.(!checked)}
      className={`relative h-[20px] w-[36px] shrink-0 rounded-full transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50 ${
        checked ? "bg-primary" : "bg-border-strong"
      }`}
    >
      <span
        className={`absolute left-0 top-[2px] h-[16px] w-[16px] rounded-full bg-white shadow-sm transition-transform ${
          checked ? "translate-x-[18px]" : "translate-x-[2px]"
        }`}
      />
    </button>
  )
}

type StatusKind = "ready" | "pending" | "active" | "failed" | "missing"
const statusStyle: Record<StatusKind, { bg: string; fg: string }> = {
  ready: { bg: "var(--status-ready-bg)", fg: "var(--status-ready)" },
  pending: { bg: "var(--status-pending-bg)", fg: "var(--status-pending)" },
  active: { bg: "var(--status-active-bg)", fg: "var(--status-active)" },
  failed: { bg: "var(--status-failed-bg)", fg: "var(--status-failed)" },
  missing: { bg: "var(--status-missing-bg)", fg: "var(--status-missing)" },
}

// Icons double the color signal so status never relies on hue alone.
const statusIcon: Record<StatusKind, ReactNode> = {
  ready: <path d="M2.5 6.2l2.2 2.2L9.5 3.6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" fill="none" />,
  pending: <><circle cx="6" cy="6" r="4.2" stroke="currentColor" strokeWidth="1.2" fill="none" /><path d="M6 3.8V6l1.6 1" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" fill="none" /></>,
  active: <path d="M6 2.2v3.8m0 0l2.4 2.4M6 6L3.6 8.4" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" fill="none" />,
  failed: <path d="M3.4 3.4l5.2 5.2M8.6 3.4L3.4 8.6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />,
  missing: <path d="M3 6h6" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />,
}

export function StatusBadge({
  kind,
  label,
}: {
  kind: StatusKind
  label: string
}) {
  const s = statusStyle[kind]
  return (
    <span
      className="inline-flex items-center gap-1 rounded-full px-2 py-[2px] text-[11px] font-medium leading-none"
      style={{ background: s.bg, color: s.fg }}
    >
      <svg width="12" height="12" viewBox="0 0 12 12">{statusIcon[kind]}</svg>
      {label}
    </span>
  )
}

const fileStateMap: Record<string, { kind: StatusKind; label: string }> = {
  ready: { kind: "ready", label: "已存在" },
  missing: { kind: "missing", label: "缺失" },
  downloading: { kind: "active", label: "下载中" },
  failed: { kind: "failed", label: "失败" },
  pending: { kind: "pending", label: "待下载" },
}

export function FileBadge({ state }: { state: FileState | "pending" }) {
  const m = fileStateMap[state] ?? fileStateMap.missing
  return <StatusBadge kind={m.kind} label={m.label} />
}

export function ProgressBar({
  value,
  indeterminate,
  tone = "active",
}: {
  value: number
  indeterminate?: boolean
  tone?: "active" | "ready" | "failed"
}) {
  const color =
    tone === "ready" ? "var(--status-ready)" : tone === "failed" ? "var(--status-failed)" : "var(--primary)"
  return (
    <div className="h-[6px] w-full overflow-hidden rounded-full bg-secondary">
      {indeterminate ? (
        <div className="h-full w-1/3 animate-[slide_1.3s_ease-in-out_infinite] rounded-full" style={{ background: color }} />
      ) : (
        <div className="h-full rounded-full transition-[width] duration-300" style={{ width: `${value}%`, background: color }} />
      )}
    </div>
  )
}

export function Segmented({
  options,
  value,
  onChange,
}: {
  options: { value: string; label: string }[]
  value: string
  onChange: (v: string) => void
}) {
  return (
    <div className="inline-flex rounded-[6px] border border-border-strong bg-secondary p-[2px]">
      {options.map((o) => (
        <button
          key={o.value}
          onClick={() => onChange(o.value)}
          className={`rounded-[4px] px-2.5 py-1 text-[12px] font-medium transition-colors ${
            value === o.value
              ? "bg-card text-foreground shadow-sm"
              : "text-muted-foreground hover:text-foreground"
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}
