import { Menu } from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { Sheet, SheetContent, SheetDescription, SheetTitle } from '@/components/ui/sheet'
import { Toaster } from '@/components/ui/sonner'
import { useApp } from '@/store/app'
import { AppSidebar, SidebarBody } from './AppSidebar'
import { CommandPalette } from './CommandPalette'
import { RunForm } from '@/dialogs/RunForm'
import { MemoSheet } from '@/dialogs/MemoSheet'
import { ProductSheet } from '@/dialogs/ProductSheet'
import { UploadReviewSheet } from '@/dialogs/UploadReviewSheet'
import { HypothesesSheet } from '@/dialogs/HypothesesSheet'
import { Logo } from './Logo'

function useTheme() {
  const theme = useApp((s) => s.ui.theme)
  useEffect(() => {
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const apply = () => document.documentElement.classList.toggle('dark', theme === 'dark' || (theme === 'system' && mq.matches))
    apply(); mq.addEventListener('change', apply)
    return () => mq.removeEventListener('change', apply)
  }, [theme])
}

export function AppShell({ children }: { children: ReactNode }) {
  useTheme()
  const nav = useNavigate(); const loc = useLocation()
  const setUI = useApp((s) => s.setUI)
  const [drawer, setDrawer] = useState(false)
  useEffect(() => setDrawer(false), [loc.pathname])
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey
      if (!mod) return
      const k = e.key.toLowerCase()
      const ui = useApp.getState().ui
      if (k === 'k') { e.preventDefault(); setUI({ commandOpen: !ui.commandOpen }) }
      else if (k === 'b') { e.preventDefault(); setUI({ sidebarOpen: !ui.sidebarOpen }) }
      else if (k === '/') { e.preventDefault(); setUI({ askOpen: !ui.askOpen }) }
      else if (k === 'n' && !e.shiftKey) { e.preventDefault(); nav('/') }
      else if (k === 'r' && e.shiftKey) { e.preventDefault(); setUI({ runFormOpen: true }) }
    }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [nav, setUI])
  return (
    <div className="flex h-dvh w-full overflow-hidden bg-background">
      <AppSidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex h-12 shrink-0 items-center gap-2 border-b px-3 md:hidden">
          <button aria-label="Open menu" onClick={() => setDrawer(true)} className="rounded-md border bg-background p-2 hover:bg-accent"><Menu className="size-5" /></button>
          <Logo /><span className="text-sm font-semibold">Eco Value Simulator</span>
        </div>
        <main className="flex min-h-0 flex-1 flex-col">{children}</main>
      </div>
      <Sheet open={drawer} onOpenChange={setDrawer}>
        <SheetContent side="left" className="w-[280px] bg-sidebar p-0">
          <SheetTitle className="sr-only">Menu</SheetTitle><SheetDescription className="sr-only">Navigation</SheetDescription>
          <SidebarBody onNavigate={() => setDrawer(false)} />
        </SheetContent>
      </Sheet>
      <CommandPalette /><RunForm /><MemoSheet /><HypothesesSheet /><ProductSheet /><UploadReviewSheet /><Toaster position="bottom-right" />
    </div>
  )
}
