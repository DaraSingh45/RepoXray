import { ReactNode, useEffect, useState } from 'react'
import { useCountUp } from '../lib/motion'
import { Check, Copy } from 'lucide-react'

export function Section({ title, lede, actions, children }: { title: string; lede?: ReactNode; actions?: ReactNode; children: ReactNode }) {
  return (
    <section className="space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div className="space-y-1.5">
          <h2 className="h-section">{title}</h2>
          {lede && <p className="lede text-sm">{lede}</p>}
        </div>
        {actions}
      </header>
      {children}
    </section>
  )
}

export function Panel({ title, aside, children, className = '' }: { title?: ReactNode; aside?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <div className={`panel p-5 ${className}`}>
      {(title || aside) && (
        <div className="mb-4 flex items-center justify-between gap-3">
          {title && <h3 className="h-block">{title}</h3>}
          {aside}
        </div>
      )}
      {children}
    </div>
  )
}

/** Counts up from 0 for plain numbers ("9,586" or 9586); other values render as-is. */
export function Num({ value }: { value: number }) {
  const n = useCountUp(value)
  return <>{Math.round(n).toLocaleString()}</>
}

export function Stat({ value, label, hint }: { value: ReactNode; label: string; hint?: string }) {
  const numeric = typeof value === 'number' ? value : typeof value === 'string' && /^\d[\d,]*$/.test(value) ? Number(value.replace(/,/g, '')) : null
  return (
    <div data-tip={hint}>
      <div className="text-2xl font-semibold tabular-nums text-paper">{numeric !== null ? <Num value={numeric} /> : value}</div>
      <div className="text-xs text-paper-mute mt-0.5">{label}</div>
    </div>
  )
}

const tones: Record<string, string> = {
  high: 'bg-bad/15 text-bad border-bad/30', medium: 'bg-warn/15 text-warn border-warn/30', low: 'bg-paper-mute/10 text-paper-dim border-ink-400',
  major: 'bg-bad/15 text-bad border-bad/30', minor: 'bg-warn/15 text-warn border-warn/30', patch: 'bg-contour/10 text-contour border-contour/30',
  current: 'bg-ok/15 text-ok border-ok/30', unpinned: 'bg-paper-mute/10 text-paper-dim border-ink-400',
  GET: 'bg-ok/15 text-ok border-ok/30', POST: 'bg-contour/15 text-contour-glow border-contour/30', PUT: 'bg-warn/15 text-warn border-warn/30',
  PATCH: 'bg-warn/15 text-warn border-warn/30', DELETE: 'bg-bad/15 text-bad border-bad/30',
}
export function Tag({ tone, children }: { tone?: string; children: ReactNode }) {
  return <span className={`inline-flex shrink-0 items-center whitespace-nowrap rounded border px-1.5 py-px text-2xs font-medium ${tones[tone ?? ''] ?? 'border-ink-400 text-paper-dim'}`}>{children}</span>
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="panel-quiet border-dashed p-8 text-center">
      <div className="font-medium text-paper">{title}</div>
      {children && <div className="mt-1.5 text-sm text-paper-mute max-w-md mx-auto">{children}</div>}
    </div>
  )
}

export function CopyBtn({ text, className = '' }: { text: string; className?: string }) {
  const [ok, setOk] = useState(false)
  return (
    <button
      className={`text-paper-mute hover:text-paper p-1 rounded ${className}`}
      aria-label="Copy to clipboard" data-tip={ok ? 'Copied' : 'Copy'}
      onClick={() => { navigator.clipboard?.writeText(text); setOk(true); setTimeout(() => setOk(false), 1200) }}
    >
      {ok ? <Check size={14} className="text-ok" /> : <Copy size={14} />}
    </button>
  )
}

export function Bar({ value, max = 100, tone }: { value: number; max?: number; tone?: 'ok' | 'warn' | 'bad' | 'contour' }) {
  const target = Math.max(0, Math.min(100, (value / (max || 1)) * 100))
  const [pct, setPct] = useState(0)
  useEffect(() => { const t = requestAnimationFrame(() => setPct(target)); return () => cancelAnimationFrame(t) }, [target])
  const t = tone ?? (target >= 75 ? 'ok' : target >= 50 ? 'warn' : 'bad')
  const cls = { ok: 'bg-ok', warn: 'bg-warn', bad: 'bg-bad', contour: 'bg-contour' }[t]
  return <div className="h-1.5 w-full rounded-full bg-ink-500 overflow-hidden"><div className={`h-full ${cls}`} style={{ width: `${pct}%`, transition: 'width 1s cubic-bezier(.2,.7,.2,1)' }} /></div>
}

export function Spinner({ size = 16 }: { size?: number }) {
  return <span className="inline-block animate-spin rounded-full border-2 border-contour border-t-transparent" style={{ width: size, height: size }} />
}

/** Readable Recharts tooltip: light text on a dark card. */
export const chartTip = {
  contentStyle: { background: '#0A1320', border: '1px solid #556E94', borderRadius: 6, fontSize: 12, padding: '6px 10px' },
  labelStyle: { color: '#E7EEF6', fontWeight: 600, marginBottom: 2 },
  itemStyle: { color: '#E7EEF6' },
  cursor: { fill: '#1B2D47' },
}

export const LAYER_COLORS: Record<string, string> = {
  'UI / Presentation': '#7FB2F0', 'API / Routing': '#4FC3C7', 'Business Logic': '#C69BF2', Core: '#9FD99A',
  'Data & Models': '#F0A04B', 'Utilities & Config': '#8A9BB5', Tests: '#6CCB8B', 'Docs & Examples': '#EF8F8C',
}
