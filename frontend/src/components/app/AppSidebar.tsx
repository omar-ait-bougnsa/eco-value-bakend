import { Box, ChevronsUpDown, MoreHorizontal, Moon, Plus, RotateCcw, Search, Settings, Sun, Monitor, Upload } from 'lucide-react'
import { NavLink, useLocation, useNavigate } from 'react-router-dom'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { report } from '@/lib/api'
import { useApp } from '@/store/app'
import { cn } from '@/lib/utils'
import { Dot } from '@/components/sim/atoms'
import { useFreshness } from './FreshnessChip'
import { Mascot } from './Mascot'
import { SIDEBAR, useSidebar } from './use-sidebar'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { toast } from 'sonner'
import { differenceInCalendarDays } from 'date-fns'

function group(createdAt: string): string {
  const days = differenceInCalendarDays(new Date(), new Date(createdAt))
  if (days <= 0) return 'Today'
  if (days === 1) return 'Yesterday'
  if (days <= 7) return 'Previous 7 days'
  return 'Older'
}

/** Shared look for every sidebar destination. Active comes from the route: NavLink sets aria-current="page". */
const navItem = 'group relative flex items-center rounded-md text-sm text-sidebar-foreground/80 outline-none transition-colors hover:bg-white/5 hover:text-sidebar-foreground focus-visible:ring-2 focus-visible:ring-[#6DB33F] aria-[current=page]:bg-white/10 aria-[current=page]:font-semibold aria-[current=page]:text-white [&_svg]:size-4 [&_svg]:shrink-0 [&_svg]:text-sidebar-foreground/60 aria-[current=page]:[&_svg]:text-white'
const activeBar = <span aria-hidden className="absolute inset-y-1.5 left-0 hidden w-[3px] rounded-full bg-[#6DB33F] group-aria-[current=page]:block" />

function Item({ to, icon, children, dot, end, title, className }: { to: string; icon?: React.ReactNode; children: React.ReactNode; dot?: boolean; end?: boolean; title?: string; className?: string }) {
  return (
    <NavLink to={to} end={end} title={title} className={cn(navItem, 'h-8 gap-2 pl-3 pr-2', className)}>
      {activeBar}
      {icon}
      <span className="min-w-0 flex-1 truncate">{children}</span>
      {dot && <Dot tone="warning" className="shrink-0" />}
    </NavLink>
  )
}

/** Icon-only destination for the collapsed rail, labelled by a tooltip. */
function RailItem({ label, to, onClick, dot, children }: { label: string; to?: string; onClick?: () => void; dot?: boolean; children: React.ReactNode }) {
  const cls = cn(navItem, 'size-10 justify-center')
  const inner = <>{activeBar}{children}{dot && <Dot tone="warning" className="absolute right-1.5 top-1.5" />}</>
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        {to ? <NavLink to={to} aria-label={label} className={cls}>{inner}</NavLink> : <button type="button" aria-label={label} onClick={onClick} className={cls}>{inner}</button>}
      </TooltipTrigger>
      <TooltipContent side="right" sideOffset={8}>{label}</TooltipContent>
    </Tooltip>
  )
}

/** Collapsed sidebar: a 56px rail of icons. */
export function SidebarRail() {
  const nav = useNavigate()
  const setUI = useApp((s) => s.setUI)
  const fresh = useFreshness()
  return (
    <div className="flex h-full flex-col items-center gap-1 py-3" style={{ width: SIDEBAR.rail }}>
      <button type="button" aria-label="Eco Value Simulator, home" title="Eco Value Simulator" onClick={() => nav('/')} className="mb-1 flex size-10 items-center justify-center rounded-md outline-none focus-visible:ring-2 focus-visible:ring-[#6DB33F]"><Mascot size={30} /></button>
      <RailItem label="New simulation" onClick={() => nav('/')}><Plus /></RailItem>
      <RailItem label="Search" onClick={() => setUI({ commandOpen: true })}><Search /></RailItem>
      <div className="my-1 h-px w-6 bg-sidebar-border" />
      <RailItem label="Products" to="/products"><Box /></RailItem>
      <RailItem label="Uploads" to="/uploads" dot={fresh.warn}><Upload /></RailItem>
      <span className="flex-1" />
      <RailItem label="Parameters" to="/parameters"><Settings /></RailItem>
    </div>
  )
}

export function SidebarBody({ onNavigate }: { onNavigate?: () => void }) {
  const nav = useNavigate(); const loc = useLocation()
  const sims = useApp((s) => s.sims); const order = useApp((s) => s.order)
  const setUI = useApp((s) => s.setUI); const ui = useApp((s) => s.ui)
  const rename = useApp((s) => s.renameSim); const del = useApp((s) => s.deleteSim); const dup = useApp((s) => s.duplicateSim); const reset = useApp((s) => s.reset)
  const fresh = useFreshness()
  const groups: Record<string, string[]> = {}
  ;[...order].sort((a, b) => sims[b].createdAt.localeCompare(sims[a].createdAt)).forEach((id) => { (groups[group(sims[id].createdAt)] ??= []).push(id) })
  const go = (p: string) => { nav(p); onNavigate?.() }
  return (
    <div className="flex h-full flex-col gap-2 p-3" onClick={(e) => { if ((e.target as HTMLElement).closest('a')) onNavigate?.() }}>
      <button onClick={() => go('/')} className="flex items-center gap-2 rounded-md px-1 py-1 text-left text-sidebar-foreground">
        <Mascot size={44} className="-my-2" />
        <span className="min-w-0 truncate text-sm font-semibold">Eco Value Simulator</span>
      </button>
      <button onClick={() => go('/')} className="flex h-[34px] items-center gap-1.5 rounded-md border border-sidebar-border bg-sidebar-accent px-3 text-sm font-medium text-sidebar-foreground transition-colors hover:bg-sidebar-accent/70">
        <Plus className="size-3.5 text-sidebar-primary" /> New simulation <span className="ml-auto text-[13px] font-normal text-sidebar-foreground/70">⌘N</span>
      </button>
      <button onClick={() => setUI({ commandOpen: true })} className="flex h-8 items-center gap-2 rounded-md px-2.5 text-sm text-sidebar-foreground/80 hover:bg-sidebar-accent hover:text-sidebar-foreground">
        <Search className="size-3.5" /> Search <span className="ml-auto text-[13px]">⌘K</span>
      </button>
      <div className="mt-1 min-h-0 flex-1 space-y-0.5 overflow-y-auto">
        <div className="px-2 pb-0.5 pt-3 text-[13px] font-medium uppercase tracking-wide text-sidebar-foreground/65">History</div>
        {['Today', 'Yesterday', 'Previous 7 days', 'Older'].filter((g) => groups[g]).map((g) => (
          <div key={g}>
            <div className="px-2 pb-0.5 pt-2 text-[13px] text-sidebar-foreground/65">{g}</div>
            {groups[g].map((id) => {
              const sim = sims[id]; const run = sim.runs[sim.runs.length - 1]
              const flagged = !!run?.output.flags.some((f) => f.severity === 'warning' || f.severity === 'error')
              return (
                <div key={id} className="group/item relative">
                  <Item to={`/s/${id}`} dot={flagged} title={sim.title} className="group-focus-within/item:pr-8 group-hover/item:pr-8">{sim.title}</Item>
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <button aria-label="Rename, duplicate or delete" title="More actions" className="absolute right-1 top-1 hidden size-6 items-center justify-center rounded text-sidebar-foreground/80 hover:bg-white/10 hover:text-white focus-visible:flex group-hover/item:flex data-[state=open]:flex"><MoreHorizontal className="size-3.5" /></button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="start" className="w-40">
                      <DropdownMenuItem onClick={() => { const t = window.prompt('Rename simulation', sim.title); if (t) rename(id, t) }}>Rename</DropdownMenuItem>
                      <DropdownMenuItem onClick={() => { dup(id).then((n) => nav(`/s/${n}`), report) }}>Duplicate</DropdownMenuItem>
                      <DropdownMenuSeparator />
                      <DropdownMenuItem onClick={() => { del(id); if (loc.pathname === `/s/${id}`) nav('/') }}>Delete</DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>
              )
            })}
          </div>
        ))}
        <div className="px-2 pb-0.5 pt-4 text-[13px] font-medium uppercase tracking-wide text-sidebar-foreground/65">Library</div>
        <Item to="/products" icon={<Box />}>Products</Item>
        <Item to="/uploads" icon={<Upload />} dot={fresh.warn}>Uploads</Item>
      </div>
      <Item to="/parameters" icon={<Settings />}>Parameters</Item>
      <div className="h-px bg-sidebar-border" />
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button className="flex items-center gap-2 rounded-md p-1.5 text-left text-sidebar-foreground hover:bg-sidebar-accent">
            <span className="flex size-7 items-center justify-center rounded-full border border-sidebar-border bg-sidebar-accent text-[13px] font-medium">PM</span>
            <span className="min-w-0 flex-1"><span className="block text-sm font-medium leading-4">Pricing manager</span><span className="block text-[13px] leading-4 text-sidebar-foreground/70">OCP · demo workspace</span></span>
            <ChevronsUpDown className="size-3.5 text-sidebar-foreground/70" />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" side="top" className="w-56">
          <DropdownMenuLabel className="text-[13px] text-muted-foreground">Theme</DropdownMenuLabel>
          <DropdownMenuItem onClick={() => setUI({ theme: 'system' })}><Monitor className="size-4" /> System {ui.theme === 'system' && '✓'}</DropdownMenuItem>
          <DropdownMenuItem onClick={() => setUI({ theme: 'light' })}><Sun className="size-4" /> Light {ui.theme === 'light' && '✓'}</DropdownMenuItem>
          <DropdownMenuItem onClick={() => setUI({ theme: 'dark' })}><Moon className="size-4" /> Dark {ui.theme === 'dark' && '✓'}</DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={() => { nav('/'); reset().then(() => toast('Demo reset'), report) }}><RotateCcw className="size-4" /> Reset demo data</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  )
}

export function AppSidebar() {
  const sb = useSidebar()
  return (
    <aside
      className={cn('relative hidden h-dvh shrink-0 border-r bg-sidebar md:block', !sb.dragging && 'transition-[width] duration-200 ease-in-out')}
      style={{ width: sb.collapsed ? SIDEBAR.rail : sb.width }}
      aria-label="Sidebar"
    >
      {/* The body keeps its full width while the aside animates, so text never reflows mid-transition. */}
      <div className="h-full overflow-hidden">
        {sb.collapsed ? <SidebarRail /> : <div className="h-full" style={{ width: sb.width }}><SidebarBody /></div>}
      </div>
      {!sb.collapsed && (
        <div
          role="separator" aria-orientation="vertical" aria-label="Resize sidebar" aria-valuemin={SIDEBAR.min} aria-valuemax={SIDEBAR.max} aria-valuenow={sb.width} tabIndex={0}
          title="Drag to resize · double-click to reset"
          onPointerDown={sb.startDrag}
          onDoubleClick={sb.resetWidth}
          onKeyDown={(e) => { if (e.key === 'ArrowLeft') { e.preventDefault(); sb.setWidth(sb.width - 16) } if (e.key === 'ArrowRight') { e.preventDefault(); sb.setWidth(sb.width + 16) } }}
          className="group absolute inset-y-0 -right-1 z-20 w-2 cursor-col-resize touch-none outline-none"
        >
          <span className={cn('absolute inset-y-0 left-1/2 w-0.5 -translate-x-1/2 bg-transparent transition-colors group-hover:bg-[#6DB33F]/70 group-focus-visible:bg-[#6DB33F]', sb.dragging && 'bg-[#6DB33F]')} />
        </div>
      )}
    </aside>
  )
}
