import { MascotIcon } from './MascotIcon'

/** The animated brand mascot, shown large on the Home hero and small in the sidebar. */
export function Mascot({ size = 160, className }: { size?: number; className?: string }) {
  return <MascotIcon size={size} className={className} animated />
}
