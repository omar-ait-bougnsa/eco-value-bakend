import { MascotIcon } from './MascotIcon'
import { cn } from '@/lib/utils'

/** The sprout mascot mark, used as the compact brand logo in bars and headers. */
export function Logo({ className, large }: { className?: string; large?: boolean }) {
  return <MascotIcon size={large ? 96 : 28} className={cn(className)} />
}
