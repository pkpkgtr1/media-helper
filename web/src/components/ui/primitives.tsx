import type { ReactNode } from "react"
import { Icon } from "./icons"

const cx = (...parts: (string | false | null | undefined)[]) => parts.filter(Boolean).join(" ")

/* ------------------------------------------------------------------ Button */

type ButtonVariant = "primary" | "accent" | "default" | "ghost" | "danger"
type ButtonSize = "sm" | "md"

const BTN_BASE =
  "inline-flex cursor-pointer select-none items-center justify-center gap-1.5 rounded-md font-medium whitespace-nowrap " +
  "transition-[background-color,border-color,color,box-shadow] duration-150 " +
  "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring " +
  "disabled:cursor-not-allowed disabled:opacity-45"

const BTN_SIZE: Record<ButtonSize, string> = {
  sm: "h-7 px-2.5 text-[12px]",
  md: "h-8 px-3 text-[13px]",
}

const BTN_VARIANT: Record<ButtonVariant, string> = {
  primary: "border border-transparent bg-primary text-primary-fg hover:bg-primary-hover",
  accent: "border border-transparent bg-accent text-accent-fg hover:brightness-110",
  default: "border border-line-strong bg-card text-fg hover:bg-elevated",
  ghost: "border border-transparent text-muted-fg hover:bg-elevated hover:text-fg",
  danger: "border border-danger/40 bg-card text-danger hover:bg-danger-soft",
}

export function Button({
  children,
  variant = "default",
  size = "md",
  disabled,
  title,
  onClick,
  type = "button",
  className,
  ariaLabel,
  full,
}: {
  children: ReactNode
  variant?: ButtonVariant
  size?: ButtonSize
  disabled?: boolean
  title?: string
  onClick?: () => void
  type?: "button" | "submit"
  className?: string
  ariaLabel?: string
  full?: boolean
}) {
  return (
    <button
      type={type}
      title={title}
      aria-label={ariaLabel}
      disabled={disabled}
      onClick={onClick}
      className={cx(BTN_BASE, BTN_SIZE[size], BTN_VARIANT[variant], full && "w-full", className)}
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
  disabled,
}: {
  children: ReactNode
  title: string
  onClick?: () => void
  active?: boolean
  disabled?: boolean
}) {
  return (
    <button
      type="button"
      title={title}
      aria-label={title}
      aria-pressed={active}
      disabled={disabled}
      onClick={onClick}
      className={cx(
        "inline-flex h-8 w-8 cursor-pointer items-center justify-center rounded-md border border-transparent",
        "text-muted-fg transition-colors duration-150 hover:bg-elevated hover:text-fg",
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
        "disabled:cursor-not-allowed disabled:opacity-45",
        active && "bg-elevated text-fg",
      )}
    >
      {children}
    </button>
  )
}

/* ------------------------------------------------------------------- Field */

export function Field({
  label,
  children,
  hint,
  width,
}: {
  label: string
  children: ReactNode
  hint?: string
  width?: string
}) {
  return (
    <label className="flex flex-col gap-1" style={width ? { width } : undefined}>
      <span className="text-[11px] font-medium tracking-wide text-muted-fg uppercase">{label}</span>
      {children}
      {hint ? <span className="text-[11px] text-muted-fg">{hint}</span> : null}
    </label>
  )
}

const INPUT =
  "h-8 w-full rounded-md border border-line-strong bg-card px-2.5 text-[13px] text-fg " +
  "transition-colors duration-150 placeholder:text-muted-fg/70 " +
  "hover:border-muted-fg/60 focus:border-ring focus:outline-none focus:ring-2 focus:ring-ring/25 " +
  "disabled:cursor-not-allowed disabled:opacity-60"

export function TextInput({
  value,
  placeholder,
  onChange,
  onEnter,
  className,
  mono,
  type = "text",
  ariaLabel,
  invalid,
  id,
}: {
  value?: string
  placeholder?: string
  onChange?: (v: string) => void
  onEnter?: () => void
  className?: string
  mono?: boolean
  type?: "text" | "password" | "url" | "number"
  ariaLabel?: string
  invalid?: boolean
  id?: string
}) {
  return (
    <input
      id={id}
      type={type}
      value={value}
      placeholder={placeholder}
      aria-label={ariaLabel}
      aria-invalid={invalid || undefined}
      onChange={(e) => onChange?.(e.target.value)}
      onKeyDown={(e) => {
        if (e.key === "Enter") {
          e.preventDefault()
          onEnter?.()
        }
      }}
      className={cx(INPUT, mono && "font-mono text-[12px]", invalid && "border-danger", className)}
    />
  )
}

export function Select<T extends string>({
  value,
  options,
  onChange,
  className,
  ariaLabel,
}: {
  value: T
  options: readonly { value: T; label: string }[] | readonly T[]
  onChange?: (v: T) => void
  className?: string
  ariaLabel?: string
}) {
  const rows = (options as readonly (T | { value: T; label: string })[]).map((o) =>
    typeof o === "string" ? { value: o, label: o } : o,
  )
  return (
    <div className={cx("relative", className)}>
      <select
        value={value}
        aria-label={ariaLabel}
        onChange={(e) => onChange?.(e.target.value as T)}
        className={cx(INPUT, "cursor-pointer appearance-none pr-7")}
      >
        {rows.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
      <span className="pointer-events-none absolute top-1/2 right-2 -translate-y-1/2 text-muted-fg">
        <Icon.chevronDown size={12} />
      </span>
    </div>
  )
}

/* ---------------------------------------------------------------- Checkbox */

export function Checkbox({
  checked,
  indeterminate,
  onChange,
  label,
}: {
  checked: boolean
  indeterminate?: boolean
  onChange?: (v: boolean) => void
  label?: string
}) {
  return (
    <button
      type="button"
      role="checkbox"
      aria-checked={indeterminate ? "mixed" : checked}
      aria-label={label}
      onClick={() => onChange?.(!checked)}
      className={cx(
        "flex h-4 w-4 shrink-0 cursor-pointer items-center justify-center rounded-[4px] border",
        "transition-colors duration-150 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
        checked || indeterminate
          ? "border-primary bg-primary text-primary-fg"
          : "border-line-strong bg-card hover:border-muted-fg",
      )}
    >
      {indeterminate ? (
        <span className="h-[2px] w-2 rounded bg-current" />
      ) : checked ? (
        <svg width="11" height="11" viewBox="0 0 12 12" fill="none" aria-hidden="true">
          <path d="M2.6 6.2l2.2 2.2L9.4 3.6" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      ) : null}
    </button>
  )
}

export function Switch({
  checked,
  onChange,
  label,
  disabled,
}: {
  checked: boolean
  onChange?: (v: boolean) => void
  label: string
  disabled?: boolean
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange?.(!checked)}
      className={cx(
        "relative h-5 w-9 shrink-0 cursor-pointer rounded-full transition-colors duration-150",
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
        "disabled:cursor-not-allowed disabled:opacity-50",
        checked ? "bg-accent" : "bg-line-strong",
      )}
    >
      <span
        className={cx(
          "absolute top-0.5 left-0.5 h-4 w-4 rounded-full bg-white shadow-sm transition-transform duration-150",
          checked && "translate-x-4",
        )}
      />
    </button>
  )
}

/* ------------------------------------------------------------ Status badge */

export type StatusKind = "ready" | "pending" | "active" | "failed" | "missing"

const STATUS_CLASS: Record<StatusKind, string> = {
  ready: "bg-ready-soft text-ready",
  pending: "bg-pending-soft text-pending",
  active: "bg-active-soft text-active",
  failed: "bg-failed-soft text-failed",
  missing: "bg-missing-soft text-missing",
}

// 图形 + 文案，状态不单靠颜色传达。
const STATUS_GLYPH: Record<StatusKind, ReactNode> = {
  ready: <path d="M2.6 6.2l2.2 2.2L9.4 3.8" />,
  pending: (
    <>
      <circle cx="6" cy="6" r="4.1" />
      <path d="M6 3.9V6l1.5 1" />
    </>
  ),
  active: <path d="M6 2.4v3.4m0 0l2.2 2.2M6 5.8L3.8 8" />,
  failed: <path d="M3.5 3.5l5 5M8.5 3.5l-5 5" />,
  missing: <path d="M3.1 6h5.8" />,
}

export function StatusBadge({ kind, label }: { kind: StatusKind; label: string }) {
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1 rounded-full px-2 py-[2px] text-[11px] leading-none font-medium",
        STATUS_CLASS[kind],
      )}
    >
      <svg
        width="12"
        height="12"
        viewBox="0 0 12 12"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        {STATUS_GLYPH[kind]}
      </svg>
      {label}
    </span>
  )
}

const FILE_STATE: Record<string, { kind: StatusKind; label: string }> = {
  ready: { kind: "ready", label: "已存在" },
  missing: { kind: "missing", label: "缺失" },
  downloading: { kind: "active", label: "下载中" },
  failed: { kind: "failed", label: "失败" },
  pending: { kind: "pending", label: "待下载" },
}

export function FileBadge({ state }: { state: string }) {
  const meta = FILE_STATE[state] ?? FILE_STATE.missing
  return <StatusBadge kind={meta.kind} label={meta.label} />
}

/* ------------------------------------------------------------- ProgressBar */

export function ProgressBar({
  value,
  indeterminate,
  tone = "active",
  label,
}: {
  value: number
  indeterminate?: boolean
  tone?: "active" | "ready" | "failed"
  label?: string
}) {
  const fill =
    tone === "ready" ? "bg-ready" : tone === "failed" ? "bg-failed" : "bg-accent"
  return (
    <div
      className="h-1.5 w-full overflow-hidden rounded-full bg-elevated"
      role="progressbar"
      aria-label={label ?? "进度"}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={indeterminate ? undefined : Math.round(value)}
      aria-valuetext={indeterminate ? "进行中" : `${Math.round(value)}%`}
    >
      {indeterminate ? (
        <div className={cx("h-full w-1/3 rounded-full", fill)} style={{ animation: "slide-bar 1.3s ease-in-out infinite" }} />
      ) : (
        <div
          className={cx("h-full rounded-full transition-[width] duration-300", fill)}
          style={{ width: `${Math.min(100, Math.max(0, value))}%` }}
        />
      )}
    </div>
  )
}

/* --------------------------------------------------------------- Segmented */

export function Segmented<T extends string>({
  options,
  value,
  onChange,
  label,
  size = "md",
}: {
  options: readonly { value: T; label: string }[]
  value: T
  onChange: (v: T) => void
  label?: string
  size?: "sm" | "md"
}) {
  return (
    <div
      role="tablist"
      aria-label={label}
      className="inline-flex flex-wrap rounded-md border border-line-strong bg-elevated p-[2px]"
    >
      {options.map((o) => {
        const active = value === o.value
        return (
          <button
            key={o.value}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(o.value)}
            className={cx(
              "cursor-pointer rounded-[4px] font-medium transition-colors duration-150",
              size === "sm" ? "px-2 py-1 text-[11px]" : "px-2.5 py-1 text-[12px]",
              "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
              active
                ? "bg-card text-fg shadow-sm"
                : "text-muted-fg hover:text-fg",
            )}
          >
            {o.label}
          </button>
        )
      })}
    </div>
  )
}

/* -------------------------------------------------------------------- Card */

export function Card({
  title,
  description,
  children,
  actions,
  className,
}: {
  title?: string
  description?: string
  children: ReactNode
  actions?: ReactNode
  className?: string
}) {
  return (
    <section className={cx("rounded-lg border border-line bg-card shadow-[var(--shadow-sm)]", className)}>
      {(title || actions) && (
        <header className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-4 py-2.5">
          <div className="min-w-0">
            {title ? <h2 className="text-[13px] font-semibold text-fg">{title}</h2> : null}
            {description ? <p className="mt-0.5 text-[12px] text-muted-fg">{description}</p> : null}
          </div>
          {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
        </header>
      )}
      <div className="px-4 py-1">{children}</div>
    </section>
  )
}

export function SettingRow({
  title,
  hint,
  children,
  muted,
}: {
  title: string
  hint?: string
  children: ReactNode
  muted?: boolean
}) {
  return (
    <div
      className={cx(
        "flex flex-col items-stretch justify-between gap-3 border-b border-line py-3.5 last:border-0",
        "sm:flex-row sm:items-center sm:gap-6",
        muted && "opacity-60",
      )}
    >
      <div className="min-w-0">
        <div className="text-[13px] font-medium text-fg">{title}</div>
        {hint ? <div className="mt-0.5 text-[12px] leading-relaxed text-muted-fg">{hint}</div> : null}
      </div>
      <div className="max-w-full shrink-0 [&>div]:max-w-full [&>div]:flex-wrap [&_input]:max-w-full">{children}</div>
    </div>
  )
}

/* ------------------------------------------------------------------- Modal */

export function Modal({
  title,
  children,
  footer,
  onClose,
  width = "max-w-[520px]",
  labelledBy = "modal-title",
}: {
  title: string
  children: ReactNode
  footer?: ReactNode
  onClose: () => void
  width?: string
  labelledBy?: string
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center p-0 sm:items-center sm:p-6">
      <div
        className="fade-in absolute inset-0 bg-[rgb(9_14_26/0.62)] backdrop-blur-[3px]"
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelledBy}
        onKeyDown={(e) => {
          if (e.key === "Escape") {
            e.stopPropagation()
            onClose()
          }
        }}
        className={cx(
          "rise-in relative flex max-h-[92vh] w-full flex-col overflow-hidden rounded-t-xl border border-line",
          "bg-card shadow-[var(--shadow-lg)] sm:rounded-xl",
          width,
        )}
      >
        <header className="flex shrink-0 items-center justify-between gap-3 border-b border-line px-4 py-3">
          <h2 id={labelledBy} className="truncate text-[14px] font-semibold text-fg">
            {title}
          </h2>
          <IconButton title="关闭" onClick={onClose}>
            <Icon.close size={16} />
          </IconButton>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">{children}</div>
        {footer ? (
          <footer className="flex shrink-0 flex-wrap items-center justify-end gap-2 border-t border-line bg-panel px-4 py-3">
            {footer}
          </footer>
        ) : null}
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------- Empty */

export function EmptyState({
  icon,
  title,
  detail,
  action,
}: {
  icon: ReactNode
  title: string
  detail?: string
  action?: ReactNode
}) {
  return (
    <div className="flex h-full min-h-[180px] flex-col items-center justify-center gap-2 px-5 py-8 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-elevated text-muted-fg">{icon}</div>
      <p className="text-[14px] font-medium text-fg">{title}</p>
      {detail ? <p className="max-w-[420px] text-[12px] leading-relaxed text-muted-fg">{detail}</p> : null}
      {action}
    </div>
  )
}

export { cx }
