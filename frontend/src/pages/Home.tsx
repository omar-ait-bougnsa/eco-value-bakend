import { PanelLeft, Sparkles } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { sendMessage } from '@/agent/chat'
import { Composer } from '@/components/sim/Thread'
import { FreshnessChip } from '@/components/app/FreshnessChip'
import { PromptSuggestion } from '@/components/ui/prompt-suggestion'
import { useEffect, useState } from 'react'
import { api, type AgentStatus } from '@/lib/api'
import { useApp } from '@/store/app'
import { Mascot } from '@/components/app/Mascot'

export default function Home() {
  const nav = useNavigate(); const setUI = useApp((s) => s.setUI); const ui = useApp((s) => s.ui); const prompts = useApp((s) => s.prompts.start)
  const [agent, setAgent] = useState<AgentStatus | null>(null)
  useEffect(() => { api.agentStatus().then(setAgent, () => setAgent(null)) }, [])
  const go = async (t: string) => { const id = await sendMessage(null, t); if (id) nav(`/s/${id}`) }
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="hidden h-14 items-center px-4 sm:px-8 md:flex">
        <button aria-label="Toggle sidebar" onClick={() => setUI({ sidebarOpen: !ui.sidebarOpen })} title="Show or hide the sidebar" className="rounded-md border bg-background p-2 text-foreground hover:bg-accent"><PanelLeft className="size-4" /></button>
      </div>
      <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-7 overflow-y-auto px-4 pb-10">
        <div className="flex flex-col items-center text-center">
          <Mascot size={176} className="-mb-2 -mt-6" />
          <h1 className="text-[28px] font-semibold tracking-tight">What do you want to price?</h1>
          <p className="mt-2 text-sm text-muted-foreground" data-testid="home-agent">{agent?.mode === 'llm' ? 'Ask in plain words. I’ll gather the data, check it, and run the engine.' : agent ? `${agent.label}. Pick one of the requests below, or word yours the same way.` : 'Pick one of the requests below.'}</p>
        </div>
        <div className="w-full max-w-[720px]"><Composer simId={null} placeholder={prompts[0] ? `${prompts[0]}…` : 'Ask the agent…'} autoFocus /></div>
        <div className="grid w-full max-w-[720px] grid-cols-1 gap-2.5 sm:grid-cols-2">
          {prompts.map((c) => (
            <PromptSuggestion key={c} onClick={() => void go(c)} className="h-auto justify-start gap-2.5 rounded-[10px] px-3.5 py-2.5 text-left text-sm font-normal">
              <Sparkles className="size-3.5 shrink-0 text-muted-foreground" /> {c}
            </PromptSuggestion>
          ))}
        </div>
      </div>
      <div className="flex shrink-0 justify-center pb-4"><FreshnessChip /></div>
    </div>
  )
}
