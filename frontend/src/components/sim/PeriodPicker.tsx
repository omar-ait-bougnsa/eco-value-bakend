import { CalendarRange, ChevronDown } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { DATA_END, DATA_START, clampPeriod, dayPeriod, monthPeriod, periodLabel, samePeriod, yearPeriod, type Period } from '@/engine/period'
import { dayLong } from '@/lib/format'
import { cn } from '@/lib/utils'

type Mode = 'day' | 'month' | 'year' | 'range'
const MODES: [Mode, string][] = [['day', 'Day'], ['month', 'Month'], ['year', 'Year'], ['range', 'Range']]
const YEARS = [2026, 2025, 2024, 2023, 2022, 2021]

function detectMode(p: Period): Mode {
  if (p.from === p.to) return 'day'
  if (YEARS.some((y) => samePeriod(p, yearPeriod(y)))) return 'year'
  const m = monthPeriod(p.from.slice(0, 7))
  if (samePeriod(p, m)) return 'month'
  return 'range'
}

export function PeriodPicker({ value, onChange, variant = 'chip', className }: { value: Period; onChange: (p: Period) => void; variant?: 'chip' | 'field'; className?: string }) {
  const [open, setOpen] = useState(false)
  const [mode, setMode] = useState<Mode>(detectMode(value))
  const [day, setDay] = useState(value.from)
  const [month, setMonth] = useState(value.from.slice(0, 7))
  const [from, setFrom] = useState(value.from)
  const [to, setTo] = useState(value.to)
  useEffect(() => { if (open) { setMode(detectMode(value)); setDay(value.from); setMonth(value.from.slice(0, 7)); setFrom(value.from); setTo(value.to) } }, [open]) // eslint-disable-line react-hooks/exhaustive-deps
  const pick = (p: Period) => { onChange(clampPeriod(p)); setOpen(false) }
  const monthOk = /^\d{4}-\d{2}$/.test(month) && month >= DATA_START.slice(0, 7) && month <= DATA_END.slice(0, 7)
  const dayOk = !!day && day >= DATA_START && day <= DATA_END
  const rangeOk = !!from && !!to && from <= to
  const apply = () => (mode === 'day' ? pick(dayPeriod(day)) : mode === 'month' ? pick(monthPeriod(month)) : pick({ from, to }))
  const disabled = mode === 'day' ? !dayOk : mode === 'month' ? !monthOk : mode === 'range' ? !rangeOk : true
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        {variant === 'chip' ? (
          <button className={cn('inline-flex h-[30px] items-center gap-1.5 rounded-md border bg-background px-2.5 text-sm hover:bg-accent', className)} aria-label="Analysis period" data-testid="period-picker">
            <CalendarRange className="size-3.5 text-muted-foreground" />
            <span className="text-[13px] text-muted-foreground">Analysis period</span>
            <span className="font-medium">{periodLabel(value)}</span>
            <ChevronDown className="size-3 text-muted-foreground" />
          </button>
        ) : (
          <button className={cn('flex h-9 w-full items-center gap-2 rounded-md border bg-background px-3 text-left text-sm', className)} aria-label="Analysis period" data-testid="period-picker">
            <CalendarRange className="size-3.5 text-muted-foreground" />
            <span className="font-medium">{periodLabel(value)}</span>
            {value.from !== value.to && <span className="num ml-1 text-[13px] text-muted-foreground">{dayLong(value.from)} → {dayLong(value.to)}</span>}
            <ChevronDown className="ml-auto size-3.5 text-muted-foreground" />
          </button>
        )}
      </PopoverTrigger>
      <PopoverContent align="start" className="w-[320px] p-3">
        <div className="grid grid-cols-4 gap-0.5 rounded-lg bg-muted p-0.5" role="tablist" aria-label="Period type">
          {MODES.map(([m, l]) => (
            <button key={m} role="tab" aria-selected={mode === m} onClick={() => setMode(m)} className={cn('rounded-md py-1.5 text-sm transition-colors', mode === m ? 'border bg-background font-medium' : 'text-muted-foreground hover:text-foreground')}>{l}</button>
          ))}
        </div>

        <div className="mt-3 min-h-[92px]">
          {mode === 'day' && (
            <label className="block space-y-1.5"><span className="text-[13px] text-muted-foreground">A single day</span>
              <Input type="date" aria-label="Day" min={DATA_START} max={DATA_END} value={day} onChange={(e) => setDay(e.target.value)} className="h-9" /></label>
          )}
          {mode === 'month' && (
            <label className="block space-y-1.5"><span className="text-[13px] text-muted-foreground">A calendar month</span>
              <Input type="month" aria-label="Month" min={DATA_START.slice(0, 7)} max={DATA_END.slice(0, 7)} value={month} onChange={(e) => setMonth(e.target.value)} className="h-9" /></label>
          )}
          {mode === 'year' && (
            <div className="space-y-1.5"><span className="text-[13px] text-muted-foreground">A calendar year</span>
              <div className="grid grid-cols-3 gap-1.5">
                {YEARS.map((y) => (
                  <button key={y} onClick={() => pick(yearPeriod(y))} className={cn('rounded-md border py-2 text-sm hover:bg-accent', samePeriod(clampPeriod(value), yearPeriod(y)) && 'border-foreground font-medium')}>{y === 2026 ? '2026 YTD' : y}</button>
                ))}
              </div></div>
          )}
          {mode === 'range' && (
            <div className="grid grid-cols-2 gap-2">
              <label className="space-y-1.5"><span className="text-[13px] text-muted-foreground">From</span><Input type="date" aria-label="From" min={DATA_START} max={DATA_END} value={from} onChange={(e) => setFrom(e.target.value)} className="h-9 text-[13px]" /></label>
              <label className="space-y-1.5"><span className="text-[13px] text-muted-foreground">To</span><Input type="date" aria-label="To" min={DATA_START} max={DATA_END} value={to} onChange={(e) => setTo(e.target.value)} className="h-9 text-[13px]" /></label>
            </div>
          )}
        </div>

        {mode !== 'year' && <div className="mt-3 flex justify-end gap-2"><Button size="sm" variant="ghost" onClick={() => setOpen(false)}>Cancel</Button><Button size="sm" disabled={disabled} onClick={apply}>Apply</Button></div>}
      </PopoverContent>
    </Popover>
  )
}
