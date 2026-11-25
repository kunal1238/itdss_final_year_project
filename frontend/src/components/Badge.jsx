import { ArrowDownRight, ArrowUpRight, Minus } from 'lucide-react'

const ICON = { BUY: ArrowUpRight, SELL: ArrowDownRight, NEUTRAL: Minus }

// Icon + word + colour: direction is never carried by colour alone.
export default function Badge({ dir, t }) {
  const Icon = ICON[dir]
  return <span className={`badge ${dir.toLowerCase()}`}><Icon size={14} aria-hidden />{t(dir)}</span>
}
