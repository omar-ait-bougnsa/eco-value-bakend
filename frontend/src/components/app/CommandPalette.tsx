import { Box, FileText, MessageSquare, Plus, Settings, Settings2, SlidersHorizontal, Upload } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { CommandDialog, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList, CommandShortcut } from '@/components/ui/command'
import { useApp } from '@/store/app'

export function CommandPalette() {
  const nav = useNavigate()
  const open = useApp((s) => s.ui.commandOpen); const setUI = useApp((s) => s.setUI)
  const sims = useApp((s) => s.sims); const order = useApp((s) => s.order); const products = useApp((s) => s.products)
  const run = (fn: () => void) => { setUI({ commandOpen: false }); setTimeout(fn, 0) }
  return (
    <CommandDialog open={open} onOpenChange={(o) => setUI({ commandOpen: o })} title="Command palette" description="Search or run a command">
      <CommandInput placeholder="Search or run a command…" />
      <CommandList className="max-h-[420px]">
        <CommandEmpty>Nothing found.</CommandEmpty>
        <CommandGroup heading="Actions">
          <CommandItem onSelect={() => run(() => nav('/'))}><Plus className="size-4" /> New simulation <CommandShortcut>⌘N</CommandShortcut></CommandItem>
          <CommandItem onSelect={() => run(() => setUI({ runFormOpen: true }))}><Settings2 className="size-4" /> Configure run <CommandShortcut>⌘⇧R</CommandShortcut></CommandItem>
          <CommandItem onSelect={() => run(() => { nav('/uploads'); setUI({ uploadReviewOpen: true }) })}><Upload className="size-4" /> Upload document</CommandItem>
          <CommandItem onSelect={() => run(() => setUI({ memoOpen: true }))}><FileText className="size-4" /> Open memo</CommandItem>
          <CommandItem onSelect={() => run(() => setUI({ hypothesesOpen: true }))}><SlidersHorizontal className="size-4" /> Open hypotheses</CommandItem>
        </CommandGroup>
        <CommandGroup heading="Simulations">
          {order.map((id) => <CommandItem key={id} value={`sim ${sims[id].title}`} onSelect={() => run(() => nav(`/s/${id}`))}><MessageSquare className="size-4" /> {sims[id].title}</CommandItem>)}
        </CommandGroup>
        <CommandGroup heading="Products">
          {products.slice(0, 6).map((p) => <CommandItem key={p.id} value={`product ${p.name}`} onSelect={() => run(() => { nav('/products'); setUI({ productSheetId: p.id }) })}><Box className="size-4" /> {p.name}</CommandItem>)}
        </CommandGroup>
        <CommandGroup heading="Pages">
          <CommandItem onSelect={() => run(() => nav('/products'))}><Box className="size-4" /> Products</CommandItem>
          <CommandItem onSelect={() => run(() => nav('/uploads'))}><Upload className="size-4" /> Uploads</CommandItem>
          <CommandItem onSelect={() => run(() => nav('/parameters'))}><Settings className="size-4" /> Parameters</CommandItem>
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  )
}
