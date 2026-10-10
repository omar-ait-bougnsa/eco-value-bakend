import { useEffect, useId, useState } from 'react'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'

/** What is wrong with a number against its bounds, in the words the server uses. Null when it fits. */
export function rangeError(v: number | null, { min, max, above, required, unit = '' }: { min?: number; max?: number; above?: boolean; required?: boolean; unit?: string }): string | null {
  if (v == null) return required ? 'is required' : null
  if (!Number.isFinite(v)) return 'must be a number'
  const u = unit ? ` ${unit}` : ''
  if (min != null && (v < min || (above && v <= min))) return max != null ? `must be ${above ? 'above' : 'between'} ${min} ${above ? 'and at most' : 'and'} ${max}${u}` : `must be ${above ? 'above' : 'at least'} ${min}${u}`
  if (max != null && v > max) return min != null ? `must be ${above ? 'above' : 'between'} ${min} ${above ? 'and at most' : 'and'} ${max}${u}` : `must be at most ${max}${u}`
  return null
}

interface Props {
  label: string
  /** The stored value. With `scale`, the field shows value × scale (a fraction as a percentage). */
  value: number | null
  onChange: (v: number | null) => void
  min?: number
  max?: number
  /** The value must be above `min`, not equal to it. */
  above?: boolean
  step?: number
  unit?: string
  scale?: number
  required?: boolean
  /** What the server says about this field. Shown instead of the bounds check when there is one. */
  error?: string | null
  placeholder?: string
  /** Label for screen readers only: the visible label is elsewhere (a table header). */
  hideLabel?: boolean
  className?: string
  inputClassName?: string
}

/**
 * A number with its unit and bounds. The bounds are the server's (GET /limits): they are checked here as the user types
 * so the mistake shows next to the field, and again by the server, which decides.
 */
export function NumberField({ label, value, onChange, min, max, above, step, unit, scale = 1, required, error, placeholder, hideLabel, className, inputClassName }: Props) {
  const id = useId()
  const shown = (v: number | null) => (v == null || !Number.isFinite(v) ? '' : String(Math.round(v * scale * 1e9) / 1e9))
  const [text, setText] = useState(shown(value))
  // Follow a value changed from outside (a reset, another product), but not the user's own half-typed number.
  useEffect(() => { if (text.trim() === '' ? value != null : Number(text) / scale !== value) setText(shown(value)) }, [value]) // eslint-disable-line react-hooks/exhaustive-deps
  const typed = text.trim() === '' ? null : Number(text)
  const local = typed != null && !Number.isFinite(typed) ? 'must be a number' : rangeError(typed, { min: min == null ? undefined : min * scale, max: max == null ? undefined : max * scale, above, required, unit })
  const problem = error ?? local
  return (
    <div className={className}>
      {!hideLabel && <label htmlFor={id} className="mb-1 block text-[13px] text-muted-foreground">{label}</label>}
      <div className="relative">
        <Input
          id={id} type="number" inputMode="decimal" aria-label={hideLabel ? label : undefined} placeholder={placeholder}
          min={min == null ? undefined : min * scale} max={max == null ? undefined : max * scale} step={step ?? 'any'} required={required}
          aria-invalid={!!problem} aria-describedby={problem ? `${id}-error` : undefined}
          className={cn('num', unit && 'pr-14', problem && 'border-danger-dot focus-visible:ring-danger-dot', inputClassName)}
          value={text}
          onChange={(e) => { const t = e.target.value; setText(t); const n = t.trim() === '' ? null : Number(t); onChange(n == null ? null : Number.isFinite(n) ? n / scale : NaN) }}
        />
        {unit && <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-[13px] text-muted-foreground">{unit}</span>}
      </div>
      {problem && <p id={`${id}-error`} role="alert" className="mt-1 text-[12px] leading-4 text-danger-fg">{label} {problem}</p>}
    </div>
  )
}
