import { useCallback, useRef, useState } from 'react'
import { useApp } from '@/store/app'

export const SIDEBAR = { min: 200, max: 400, default: 260, rail: 56 } as const
const KEY = 'evs.sidebarWidth'
const clamp = (w: number) => Math.min(SIDEBAR.max, Math.max(SIDEBAR.min, Math.round(w)))
const read = () => { try { const w = Number(localStorage.getItem(KEY)); return w ? clamp(w) : SIDEBAR.default } catch { return SIDEBAR.default } }
const save = (w: number) => { try { localStorage.setItem(KEY, String(w)) } catch { /* the width just won't be remembered */ } }

/**
 * Sidebar layout state: width (drag to resize, remembered) and collapsed/expanded.
 * Collapsed lives in the app store (`ui.sidebarOpen`), which is already persisted and toggled by the header icon and Ctrl/Cmd+B.
 */
export function useSidebar() {
  const collapsed = !useApp((s) => s.ui.sidebarOpen)
  const setUI = useApp((s) => s.setUI)
  const [width, setWidthState] = useState(read)
  const [dragging, setDragging] = useState(false)
  const latest = useRef(width)

  const setWidth = useCallback((w: number) => { const c = clamp(w); latest.current = c; setWidthState(c); save(c) }, [])
  const resetWidth = useCallback(() => setWidth(SIDEBAR.default), [setWidth])
  const toggle = useCallback(() => setUI({ sidebarOpen: collapsed }), [setUI, collapsed])

  /** Attach to the handle's onPointerDown. Tracks the pointer until release, then saves once. */
  const startDrag = useCallback((e: React.PointerEvent<HTMLElement>) => {
    e.preventDefault()
    const el = e.currentTarget
    const left = el.parentElement?.getBoundingClientRect().left ?? 0
    el.setPointerCapture(e.pointerId)
    document.body.style.userSelect = 'none'
    document.body.style.cursor = 'col-resize'
    setDragging(true)
    let frame = 0
    const move = (ev: PointerEvent) => {
      latest.current = clamp(ev.clientX - left)
      if (!frame) frame = requestAnimationFrame(() => { frame = 0; setWidthState(latest.current) })
    }
    const stop = () => {
      cancelAnimationFrame(frame)
      document.body.style.userSelect = ''
      document.body.style.cursor = ''
      el.removeEventListener('pointermove', move); el.removeEventListener('pointerup', stop); el.removeEventListener('pointercancel', stop)
      setWidthState(latest.current); save(latest.current); setDragging(false)
    }
    el.addEventListener('pointermove', move); el.addEventListener('pointerup', stop); el.addEventListener('pointercancel', stop)
  }, [])

  return { collapsed, toggle, width, setWidth, resetWidth, dragging, startDrag }
}
