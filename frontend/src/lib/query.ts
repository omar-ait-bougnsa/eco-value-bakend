import { useEffect, useState } from 'react'
import { useApp } from '@/store/app'

// Backend answers by key, so a view asked twice is fetched once.
const pending = new Map<string, Promise<unknown>>()
const done = new Map<string, unknown>()

function fetchOnce<T>(key: string, fn: () => Promise<T>): Promise<T> {
  let p = pending.get(key) as Promise<T> | undefined
  if (!p) {
    if (pending.size > 300) { pending.clear(); done.clear() }
    p = fn().then((v) => { done.set(key, v); return v }, (e) => { pending.delete(key); throw e })
    pending.set(key, p)
  }
  return p
}

/**
 * Something the backend calculates for a view. `key` names the question (null = nothing to ask);
 * it is asked again when the products, parameters or uploads change, since the answer depends on them.
 */
export function useQuery<T>(key: string | null, fn: () => Promise<T>): { data: T | undefined; loading: boolean; error: string | null } {
  const rev = useApp((s) => s.rev)
  const k = key == null ? null : `${rev}:${key}`
  const [, tick] = useState(0)
  const [failed, setFailed] = useState<{ k: string; msg: string } | null>(null)
  useEffect(() => {
    if (k == null || done.has(k)) return
    let live = true
    fetchOnce(k, fn).then(() => live && tick((n) => n + 1), (e) => live && setFailed({ k, msg: e instanceof Error ? e.message : String(e) }))
    return () => { live = false }
  }, [k]) // eslint-disable-line react-hooks/exhaustive-deps
  const data = k != null && done.has(k) ? (done.get(k) as T) : undefined
  const error = failed && failed.k === k ? failed.msg : null
  return { data, loading: k != null && data === undefined && !error, error }
}

/** `v`, a moment after it stops changing: for values typed into a form. */
export function useDebounced<T>(v: T, ms = 250): T {
  const [d, setD] = useState(v)
  useEffect(() => { const t = setTimeout(() => setD(v), ms); return () => clearTimeout(t) }, [v, ms])
  return d
}
