import { useMatch } from 'react-router-dom'
import { Sheet, SheetContent, SheetDescription, SheetTitle } from '@/components/ui/sheet'
import { useSimData } from '@/components/sim/sim-context'
import Hypotheses from '@/pages/tabs/Hypotheses'
import { useApp } from '@/store/app'

/** Hypotheses live in a drawer: reachable from the header, flags and ⌘K, but out of the main tab flow. */
export function HypothesesSheet() {
  const open = useApp((s) => s.ui.hypothesesOpen); const setUI = useApp((s) => s.setUI)
  const m = useMatch('/s/:id')
  const sim = useApp((s) => (m?.params.id ? s.sims[m.params.id] : undefined))
  const data = useSimData(sim)
  return (
    <Sheet open={open && !!data} onOpenChange={(o) => setUI({ hypothesesOpen: o })}>
      <SheetContent side="right" className="flex w-full flex-col gap-0 p-0 sm:max-w-[760px]">
        <SheetDescription className="sr-only">Editable assumptions for this simulation</SheetDescription>
        <div className="flex h-16 shrink-0 flex-col justify-center border-b pl-6 pr-14">
          <SheetTitle className="text-base">Hypotheses</SheetTitle>
          <p className="text-[13px] text-muted-foreground">Every input and where it comes from. Changes are staged and create a new version.</p>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-5" id="hyp-scroll">
          {data && <Hypotheses data={data} onDone={() => setUI({ hypothesesOpen: false })} />}
        </div>
      </SheetContent>
    </Sheet>
  )
}
