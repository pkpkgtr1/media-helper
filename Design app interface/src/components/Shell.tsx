import type { ReactNode } from "react"

export function SettingShell({ title, children }: { title?: string; children: ReactNode }) {
  return (
    <section className="rounded-[8px] border border-border bg-card px-3 sm:px-5 py-1">
      {title && (
        <h3 className="border-b border-border py-3 text-[13px] font-semibold text-foreground">
          {title}
        </h3>
      )}
      {children}
    </section>
  )
}

export function SettingRow({
  title,
  hint,
  children,
}: {
  title: string
  hint?: string
  children: ReactNode
}) {
  return (
    <div className="flex flex-col items-stretch justify-between gap-3 border-b border-border py-3.5 last:border-0 sm:flex-row sm:items-center sm:gap-6">
      <div className="min-w-0">
        <div className="text-[13px] font-medium text-foreground">{title}</div>
        {hint && (
          <div className="mt-0.5 text-[12px] leading-relaxed text-muted-foreground">
            {hint}
          </div>
        )}
      </div>
      <div className="max-w-full shrink-0 [&>div]:max-w-full [&>div]:flex-wrap [&_input]:max-w-full">
        {children}
      </div>
    </div>
  )
}

export function Modal({
  title,
  onClose,
  children,
  width = "max-w-[560px]",
}: {
  title: string
  onClose: () => void
  children: ReactNode
  width?: string
}) {
  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/40 p-4" role="dialog" aria-label={title}>
      <div className={`flex max-h-[85vh] w-full ${width} flex-col overflow-hidden rounded-[10px] border border-border-strong bg-card shadow-2xl`}>
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <h3 className="text-[14px] font-semibold text-foreground">{title}</h3>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground" aria-label="关闭">
            ✕
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">{children}</div>
      </div>
    </div>
  )
}
