import { useMemo, type ReactNode } from 'react'
import type { Components } from 'react-markdown'
import { Markdown } from '@/components/ui/markdown'
import { cn } from '@/lib/utils'
import { SourceChip } from './atoms'

interface Source { n: number; name: string; where: string }

/** `[2] argus.xlsx, 30-Sep-2026, FOB Morocco`: the number the text cites it by, the document, and where in it. */
function parseSource(s: string): Source | null {
  const m = /^\[(\d+)\]\s+(.+)$/.exec(s)
  if (!m) return null
  const [name, ...rest] = m[2].split(', ')
  return { n: +m[1], name, where: rest.join(' · ') }
}

const plain = (c: ReactNode): string => (typeof c === 'string' || typeof c === 'number' ? String(c) : Array.isArray(c) ? c.map(plain).join('') : '')
const isFigure = (s: string) => /^[−‑+-]?[\d\s.,]+%?$/.test(s.trim()) && /\d/.test(s)

const badge = 'inline-flex h-[18px] min-w-[18px] shrink-0 items-center justify-center rounded-[5px] bg-accent px-1 font-mono text-[11px] font-semibold leading-none text-accent-foreground'

/** How an answer's Markdown is drawn in the thread. `sources` gives each citation mark its document as a tooltip. */
function components(sources: Source[]): Partial<Components> {
  return {
    p: ({ children }) => <p className="leading-[1.6]">{children}</p>,
    h1: ({ children }) => <h3 className="pt-1 text-[15px] font-semibold leading-snug">{children}</h3>,
    h2: ({ children }) => <h3 className="pt-1 text-[15px] font-semibold leading-snug">{children}</h3>,
    h3: ({ children }) => <h4 className="pt-1 text-sm font-semibold leading-snug">{children}</h4>,
    h4: ({ children }) => <h4 className="pt-1 text-sm font-semibold leading-snug">{children}</h4>,
    ul: ({ children }) => <ul className="list-disc space-y-1.5 pl-5 marker:text-muted-foreground">{children}</ul>,
    ol: ({ children }) => <ol className="list-decimal space-y-1.5 pl-5 marker:font-medium marker:text-muted-foreground">{children}</ol>,
    li: ({ children }) => <li className="pl-0.5 leading-[1.55] [&>ol]:mt-1.5 [&>ul]:mt-1.5">{children}</li>,
    strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
    blockquote: ({ children }) => <blockquote className="space-y-2 border-l-2 pl-3 text-muted-foreground">{children}</blockquote>,
    hr: () => <hr className="border-border" />,
    a: ({ href, children }) => {
      const cited = href?.startsWith('#cite-') ? sources.find((s) => String(s.n) === href.slice(6)) : null
      // A plain inline box, not the flex badge of the list below: the browser may wrap a line on either side of a flex box,
      // which leaves the mark alone at the start of a line or strands the full stop after it.
      if (cited) return <span className="relative -top-px cursor-default rounded-[5px] bg-accent px-[5px] py-[1.5px] font-mono text-[11px] font-semibold text-accent-foreground" title={[cited.name, cited.where].filter(Boolean).join(' · ')}>{cited.n}</span>
      return <a href={href} target="_blank" rel="noreferrer" className="font-medium text-primary underline underline-offset-2">{children}</a>
    },
    // A table scrolls sideways inside its own frame, so a wide one never stretches the panel.
    table: ({ children }) => <div className="overflow-x-auto rounded-lg border"><table className="w-full border-collapse text-[13px] leading-5">{children}</table></div>,
    thead: ({ children }) => <thead className="bg-muted">{children}</thead>,
    tr: ({ children }) => <tr className="border-b last:border-b-0">{children}</tr>,
    th: ({ children }) => <th className="whitespace-nowrap px-2.5 py-1.5 text-left font-semibold">{children}</th>,
    td: ({ children }) => <td className={cn('px-2.5 py-1.5 align-top', isFigure(plain(children)) && 'num whitespace-nowrap')}>{children}</td>,
    code: ({ children }) => <code className="rounded bg-muted px-1 py-px font-mono text-[0.92em]">{children}</code>,
    pre: ({ children }) => <pre className="overflow-x-auto rounded-lg border bg-muted p-3 font-mono text-[13px] leading-5 [&_code]:bg-transparent [&_code]:p-0">{children}</pre>,
  }
}

/** An agent's answer: its Markdown, then where it comes from. Numbered sources (`[1] …`) are the ones the text cites. */
export function AnswerText({ text, sources = [] }: { text: string; sources?: string[] }) {
  const cited = useMemo(() => sources.map(parseSource).filter((s): s is Source => s !== null), [sources])
  const numbered = cited.length > 0 && cited.length === sources.length
  const drawn = useMemo(() => components(numbered ? cited : []), [cited, numbered])
  // A citation mark becomes a link the renderer draws as a badge. A mark with no source of that number stays as written.
  // The space before a mark is made non-breaking, so the badge never starts a line by itself.
  const body = numbered ? text.replace(/([^\s|])?[ \t]*\[(\d{1,2})\](?![([:])/g, (mark, before, n) => (cited.some((s) => s.n === +n) ? `${before ? `${before}\u00a0` : ''}[${n}](#cite-${n})` : mark)) : text
  return (
    <>
      <Markdown className="space-y-3 text-sm text-foreground [overflow-wrap:anywhere]" components={drawn}>{body}</Markdown>
      {numbered ? (
        <div className="space-y-1.5">
          <div className="text-[12px] font-medium text-muted-foreground">Sources</div>
          <ol className="divide-y overflow-hidden rounded-lg border">
            {cited.map((s) => (
              <li key={s.n} className="flex items-start gap-2.5 px-2.5 py-2">
                <span className={cn(badge, 'mt-px')}>{s.n}</span>
                <span className="min-w-0">
                  <span className="block truncate text-[13px] font-medium" title={s.name}>{s.name}</span>
                  {s.where && <span className="block truncate text-[12px] text-muted-foreground">{s.where}</span>}
                </span>
              </li>
            ))}
          </ol>
        </div>
      ) : sources.length > 0 && (
        <div className="flex flex-wrap gap-1.5">{sources.map((s) => <SourceChip key={s}>{s}</SourceChip>)}</div>
      )}
    </>
  )
}
