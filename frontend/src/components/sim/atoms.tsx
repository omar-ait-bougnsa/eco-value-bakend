import { AlertTriangle, CheckCircle2, ChevronRight, FileText, Info, OctagonAlert } from 'lucide-react'
import type { ReactNode } from 'react'
import type { Flag } from '@/engine/types'
import { cn } from '@/lib/utils'

/** Action inside a tinted banner or flag: reads as a button on any tone. */
export const bannerAction = 'inline-flex h-8 shrink-0 items-center rounded-md border border-current/40 bg-background/70 px-3 text-sm font-medium hover:bg-background'

export function SourceChip({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span className={cn('inline-flex items-center gap-1.5 rounded-md border bg-background px-2 py-[3px] font-mono text-[13px] text-muted-foreground', className)}>
      <FileText className="size-3" />
      {children}
    </span>
  )
}

export function Pill({ children, tone = 'default', className }: { children: ReactNode; tone?: 'default' | 'solid' | 'warning' | 'danger' | 'info' | 'anchor' | 'outline'; className?: string }) {
  const t = {
    default: 'bg-muted text-muted-foreground',
    solid: 'bg-primary text-primary-foreground',
    warning: 'bg-warning-bg text-warning-fg',
    danger: 'bg-danger-bg text-danger-fg',
    info: 'bg-info-bg text-info',
    anchor: 'bg-anchor text-white',
    outline: 'border text-muted-foreground',
  }[tone]
  return <span className={cn('inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-[13px] font-medium', t, className)}>{children}</span>
}

export function Dot({ tone = 'warning', className }: { tone?: 'warning' | 'danger' | 'info' | 'fg'; className?: string }) {
  return <span className={cn('inline-block size-1.5 rounded-full', tone === 'warning' ? 'bg-warning-dot' : tone === 'danger' ? 'bg-danger-dot' : tone === 'info' ? 'bg-info' : 'bg-foreground', className)} />
}

export function Card({ title, sub, actions, children, className, bodyClassName }: { title?: ReactNode; sub?: ReactNode; actions?: ReactNode; children?: ReactNode; className?: string; bodyClassName?: string }) {
  return (
    <section className={cn('rounded-xl border bg-card p-6', className)}>
      {(title || actions) && (
        <header className="mb-4 flex items-start justify-between gap-3">
          <div className="min-w-0">
            {title && <h3 className="text-base font-semibold leading-6 tracking-tight">{title}</h3>}
            {sub && <p className="mt-0.5 text-[13px] text-muted-foreground">{sub}</p>}
          </div>
          {actions}
        </header>
      )}
      <div className={bodyClassName}>{children}</div>
    </section>
  )
}

export function Kpi({ label, value, unit, delta, className }: { label: string; value: ReactNode; unit?: string; delta?: ReactNode; className?: string }) {
  return (
    <div className={cn('rounded-xl border bg-card p-5', className)}>
      <div className="text-sm text-muted-foreground">{label}</div>
      <div className="mt-1.5 flex items-end gap-1.5">
        <span className="num text-[32px] font-medium leading-9 tracking-tight">{value}</span>
        {unit && <span className="pb-1 text-[13px] text-muted-foreground">{unit}</span>}
      </div>
      {delta && <div className="num mt-1.5 text-[13px] text-muted-foreground">{delta}</div>}
    </div>
  )
}

export function FlagIcon({ sev, className }: { sev: Flag['severity']; className?: string }) {
  const c = cn('size-4 shrink-0', className)
  if (sev === 'error') return <OctagonAlert className={cn(c, 'text-danger-fg')} />
  if (sev === 'warning') return <AlertTriangle className={cn(c, 'text-warning-fg')} />
  if (sev === 'resolved') return <CheckCircle2 className={cn(c, 'text-primary')} />
  return <Info className={cn(c, 'text-info')} />
}

export function FlagRow({ flag, onAction, dense }: { flag: Flag; onAction?: (f: Flag) => void; dense?: boolean }) {
  return (
    <button
      type="button"
      onClick={() => onAction?.(flag)}
      className="group flex w-full items-center gap-2.5 rounded-lg border px-3 py-2 text-left text-sm transition-colors hover:bg-accent/60"
    >
      <FlagIcon sev={flag.severity} />
      <span className={cn('min-w-0 flex-1 truncate', flag.severity === 'resolved' && 'text-muted-foreground line-through decoration-muted-foreground/40')}>{flag.title}</span>
      {!dense && flag.action && <span className="shrink-0 text-sm font-medium text-primary group-hover:underline">{flag.action.label}</span>}
      <ChevronRight className="size-4 shrink-0 text-muted-foreground" />
    </button>
  )
}

export function FlagBanner({ flag, onAction }: { flag: Flag; onAction?: (f: Flag) => void }) {
  const tone = flag.severity === 'error' ? 'bg-danger-bg text-danger-fg' : flag.severity === 'warning' ? 'bg-warning-bg text-warning-fg' : flag.severity === 'info' ? 'bg-info-bg text-info' : 'bg-muted text-foreground'
  return (
    <div className={cn('flex items-start gap-2.5 rounded-lg p-3', tone)}>
      <FlagIcon sev={flag.severity} className={flag.severity === 'info' ? '' : 'text-current'} />
      <div className="min-w-0 flex-1">
        <div className="text-sm font-medium">{flag.title}</div>
        {flag.detail && <div className="mt-0.5 text-[13px] text-muted-foreground">{flag.detail}</div>}
      </div>
      {flag.action && (
        <button className={bannerAction} onClick={() => onAction?.(flag)}>{flag.action.label}</button>
      )}
    </div>
  )
}
