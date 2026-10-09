import { Navigate, Route, BrowserRouter, Routes } from 'react-router-dom'
import { TooltipProvider } from '@/components/ui/tooltip'
import { AppShell } from '@/components/app/AppShell'
import Home from '@/pages/Home'
import Simulation from '@/pages/Simulation'
import Products from '@/pages/Products'
import Uploads from '@/pages/Uploads'
import Parameters from '@/pages/Parameters'
import { useEffect, type ReactNode } from 'react'
import { Button } from '@/components/ui/button'
import { useApp } from '@/store/app'

/** Loads the data from the backend before the app renders. */
function Boot({ children }: { children: ReactNode }) {
  const status = useApp((s) => s.status); const error = useApp((s) => s.error); const load = useApp((s) => s.load)
  useEffect(() => { void load() }, [load])
  if (status === 'ready') return <>{children}</>
  return (
    <div className="flex h-dvh flex-col items-center justify-center gap-3 bg-background p-6 text-center">
      {status === 'loading' ? <p className="text-sm text-muted-foreground">Loading…</p> : (
        <>
          <p className="text-sm font-medium">Could not load the data</p>
          <p className="max-w-sm text-sm text-muted-foreground">{error}</p>
          <Button variant="outline" onClick={() => void load()}>Try again</Button>
        </>
      )}
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <TooltipProvider delayDuration={200}>
        <Boot><AppShell>
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/s/:id" element={<Simulation />} />
            <Route path="/products" element={<Products />} />
            <Route path="/uploads" element={<Uploads />} />
            <Route path="/parameters" element={<Parameters />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </AppShell></Boot>
      </TooltipProvider>
    </BrowserRouter>
  )
}
