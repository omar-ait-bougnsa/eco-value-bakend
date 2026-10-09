import { useEffect, useRef, useState } from 'react'
import { cn } from '@/lib/utils'

/**
 * The Eco Value plant mascot — the brand mark used in the sidebar, mobile header and Home hero.
 * `animated` adds the idle loop (sway, breathe, blink, blush) and the happy face on hover or click.
 * Styles live under "Mascot" in index.css.
 */
export function MascotIcon({ size = 40, className, animated = false }: { size?: number; className?: string; animated?: boolean }) {
  const [happy, setHappy] = useState(false)
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined)
  useEffect(() => () => clearTimeout(timer.current), [])
  const cheer = () => { setHappy(true); clearTimeout(timer.current); timer.current = setTimeout(() => setHappy(false), 1400) }
  // The ground shadow only reads at hero size; small marks stay a clean flat logo.
  const shadow = animated && size >= 120
  const vbH = shadow ? 560 : 536
  const height = (size * 212) / 192
  return (
    <svg
      width={(height * 326) / vbH}
      height={height}
      viewBox={`30 0 326 ${vbH}`}
      role="img"
      aria-label="Eco Value Simulator"
      onClick={animated ? cheer : undefined}
      className={cn('mascot shrink-0 overflow-visible', animated && 'mascot-animated', happy && 'mascot-happy', className)}
    >
      {shadow && <ellipse className="mascot-shadow" cx="185" cy="545" rx="125" ry="10" />}
      <g className="mascot-char">
        <g className="mascot-breathe">
          <path className="mascot-leaf-left" fill="#6DB33F" d="M186 148 C122 144 58 86 36 14 C112 6 178 62 186 148 Z" />
          <path className="mascot-leaf-right" fill="#2E7D32" d="M188 148 C196 64 266 10 350 2 C332 92 262 142 188 148 Z" />
          <rect x="176" y="108" width="20" height="52" rx="10" fill="#2E7D32" />
          <path fill="#6DB33F" d="M185 148 C272 148 320 212 320 300 C320 384 262 436 185 436 C108 436 52 384 52 300 C52 212 98 148 185 148 Z" />
          {/* One group, so both eyes always blink as a single movement. */}
          <g className="mascot-eyes" fill="#0F1F1A">
            <circle cx="140" cy="248" r="17" />
            <circle cx="230" cy="248" r="17" />
          </g>
          <ellipse className="mascot-cheek" cx="109" cy="292" rx="19" ry="11" fill="#C8A876" />
          <ellipse className="mascot-cheek" cx="261" cy="292" rx="19" ry="11" fill="#C8A876" />
          <path className="mascot-smile" d="M162 292 Q186 312 210 291" fill="none" stroke="#0F1F1A" strokeWidth="9" strokeLinecap="round" />
          <path className="mascot-smile-big" d="M158 286 Q186 326 214 286 Z" fill="#0F1F1A" stroke="#0F1F1A" strokeWidth="6" strokeLinejoin="round" />
        </g>
        <polygon points="66,462 304,462 292,530 78,530" fill="#D9C49A" />
        <rect x="40" y="420" width="290" height="44" rx="18" fill="#8B5A1E" />
      </g>
    </svg>
  )
}
