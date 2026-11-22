import { useCallback, useEffect, useId, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Download, Maximize2, Minimize2, Minus, Pause, Play, Plus, RotateCcw, ScanSearch } from 'lucide-react'
import { CopyBtn } from './ui'
import { useReducedMotion } from '../lib/motion'

type MermaidAPI = typeof import('mermaid').default
let ready: Promise<MermaidAPI> | null = null

function loadMermaid() {
  if (!ready) {
    ready = Promise.all([import('mermaid'), import('@mermaid-js/layout-elk')]).then(([m, elk]) => {
      try { m.default.registerLayoutLoaders(elk.default) } catch { /* already registered */ }
      m.default.initialize({
        startOnLoad: false, securityLevel: 'strict', theme: 'base', fontFamily: 'IBM Plex Sans',
        // ELK routes edges around nodes, which keeps dense diagrams readable
        layout: 'dagre',
        elk: { mergeEdges: false, nodePlacementStrategy: 'BRANDES_KOEPF', considerModelOrder: 'NODES_AND_EDGES' },
        flowchart: { curve: 'basis', htmlLabels: true, padding: 14, nodeSpacing: 46, rankSpacing: 64, wrappingWidth: 220 },
        sequence: { actorMargin: 70, messageMargin: 44, boxMargin: 12, mirrorActors: false, useMaxWidth: false },
        mindmap: { padding: 16, useMaxWidth: false },
        themeVariables: {
          background: '#0F1B2D', primaryColor: '#15243A', primaryTextColor: '#E7EEF6', primaryBorderColor: '#4FC3C7',
          lineColor: '#7F98BC', secondaryColor: '#1B2D47', tertiaryColor: '#0B1524', clusterBkg: '#0B152499',
          clusterBorder: '#556E94', edgeLabelBackground: '#0F1B2D', fontSize: '16px', actorBkg: '#15243A',
          actorBorder: '#4FC3C7', actorTextColor: '#E7EEF6', actorLineColor: '#556E94', signalColor: '#C9D5E3',
          signalTextColor: '#E7EEF6', noteBkgColor: '#1B2D47', noteTextColor: '#E7EEF6', labelBoxBkgColor: '#15243A',
          sequenceNumberColor: '#0B1524', titleColor: '#E7EEF6',
        },
      } as any)
      return m.default
    })
  }
  return ready
}

const isFlowchart = (src: string) => /^\s*(flowchart|graph)\s/m.test(src.replace(/^---[\s\S]*?---\s*/, ''))

/** Renders Mermaid with ELK layout, pan/zoom, an orchestrated entrance, flowing edges and hover tracing.
 *  If `code` fails to render, `fallback` is tried; failing both, the source is shown. */
export default function Mermaid({ code, fallback, title, engine: initialEngine = 'dagre' }: { code: string; fallback?: string; title?: string; engine?: 'elk' | 'dagre' }) {
  const [engine, setEngine] = useState<'elk' | 'dagre'>(initialEngine)
  const uid = 'm' + useId().replace(/[^a-zA-Z0-9]/g, '')
  const reduced = useReducedMotion()
  const [svg, setSvg] = useState('')
  const [err, setErr] = useState('')
  const [full, setFull] = useState(false)
  const [flow, setFlow] = useState(true)
  const [replay, setReplay] = useState(0)
  const [view, setView] = useState({ s: 1, x: 0, y: 0 })
  const [natural, setNatural] = useState({ w: 0, h: 0 })
  const box = useRef<HTMLDivElement>(null)
  const stage = useRef<HTMLDivElement>(null)
  const drag = useRef<{ x: number; y: number; vx: number; vy: number } | null>(null)

  // ---- render -------------------------------------------------------------
  useEffect(() => {
    let alive = true
    setErr(''); setSvg('')
    ;(async () => {
      const m = await loadMermaid()
      const attempts: string[] = []
      const other = engine === 'elk' ? 'dagre' : 'elk'
      for (const src of [code, fallback]) {
        if (!src) continue
        if (isFlowchart(src)) {
          attempts.push(`---\nconfig:\n  layout: ${engine}\n---\n${src}`)
          attempts.push(`---\nconfig:\n  layout: ${other}\n---\n${src}`) // if the chosen engine fails
        } else attempts.push(src)
      }
      for (const [i, src] of attempts.entries()) {
        try {
          await m.parse(src)
          const out = await m.render(`${uid}-${i}-${Date.now()}`, src)
          if (alive) setSvg(out.svg)
          return
        } catch (e: any) {
          if (alive && i === attempts.length - 1) setErr(String(e?.message || e).slice(0, 300))
        }
      }
    })()
    return () => { alive = false }
  }, [code, fallback, uid, engine])

  // ---- fit to the box -------------------------------------------------------
  const fit = useCallback(() => {
    const el = stage.current?.querySelector('svg')
    if (!el || !box.current) return
    const vb = el.viewBox?.baseVal
    const w = vb?.width || el.getBoundingClientRect().width
    const h = vb?.height || el.getBoundingClientRect().height
    el.setAttribute('width', String(w)); el.setAttribute('height', String(h))
    el.style.maxWidth = 'none'
    setNatural({ w, h })
    const bw = box.current.clientWidth - 24
    const bh = full ? box.current.clientHeight - 24 : 700
    const s = Math.max(0.72, Math.min(1.1, bw / w, bh / h))
    setView({ s, x: Math.max(12, (bw - w * s) / 2 + 12), y: full ? Math.max(12, (bh - h * s) / 2 + 12) : 12 })
  }, [full])

  // ---- animate + wire up hover ---------------------------------------------
  useEffect(() => {
    const root = stage.current?.querySelector('svg')
    if (!root) return
    fit()
    if (!reduced) animate(root)
    return wireHover(root)
  }, [svg, replay, reduced, fit])

  useEffect(() => { fit() }, [full, fit])
  useEffect(() => {
    if (!full) return
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && setFull(false)
    window.addEventListener('keydown', esc)
    return () => window.removeEventListener('keydown', esc)
  }, [full])
  useEffect(() => {
    const on = () => fit()
    window.addEventListener('resize', on)
    return () => window.removeEventListener('resize', on)
  }, [fit])

  // ---- pan & zoom ------------------------------------------------------------
  const zoomAt = (factor: number, cx?: number, cy?: number) => setView((v) => {
    const s = Math.min(3, Math.max(0.2, v.s * factor))
    const r = box.current!.getBoundingClientRect()
    const px = cx ?? r.width / 2, py = cy ?? r.height / 2
    return { s, x: px - ((px - v.x) * s) / v.s, y: py - ((py - v.y) * s) / v.s }
  })
  useEffect(() => {
    const el = box.current
    if (!el) return
    const wheel = (e: WheelEvent) => {
      if (!(e.ctrlKey || e.metaKey) && !full) return // normal scrolling keeps working
      e.preventDefault()
      const r = el.getBoundingClientRect()
      zoomAt(e.deltaY < 0 ? 1.12 : 1 / 1.12, e.clientX - r.left, e.clientY - r.top)
    }
    el.addEventListener('wheel', wheel, { passive: false })
    return () => el.removeEventListener('wheel', wheel)
  })

  const download = () => {
    const blob = new Blob([svg], { type: 'image/svg+xml' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `${(title || 'diagram').toLowerCase().replace(/\W+/g, '-')}.svg`
    a.click()
  }

  if (err) {
    return (
      <div className="text-sm text-paper-mute">
        This diagram could not be drawn ({err}).
        <pre className="mt-2 max-h-60 overflow-auto rounded bg-ink-900 p-3 font-mono text-xs">{code}</pre>
      </div>
    )
  }

  const height = full ? '100%' : `${Math.min(720, Math.max(200, natural.h * view.s + 26))}px`
  const btn = 'p-1.5 rounded text-paper-dim hover:text-paper hover:bg-ink-600'
  const body = (
    <div className={full ? 'fixed inset-0 z-50 flex flex-col bg-ink-900 p-4' : 'relative'}>
      <div className="mb-2 ml-auto flex w-fit flex-wrap items-center gap-0.5 rounded-lg border border-ink-500 bg-ink-800 p-1">
        <button className={btn} onClick={() => zoomAt(1 / 1.2)} aria-label="Zoom out" data-tip="Zoom out"><Minus size={15} /></button>
        <span className="w-11 text-center text-xs tabular-nums text-paper-dim">{Math.round(view.s * 100)}%</span>
        <button className={btn} onClick={() => zoomAt(1.2)} aria-label="Zoom in" data-tip="Zoom in"><Plus size={15} /></button>
        <button className={btn} onClick={fit} aria-label="Fit to view" data-tip="Fit to view"><ScanSearch size={15} /></button>
        <span className="mx-1 h-4 w-px bg-ink-500" />
        {!reduced && <button className={btn} onClick={() => setReplay((r) => r + 1)} aria-label="Replay animation" data-tip="Replay animation"><RotateCcw size={15} /></button>}
        {!reduced && isFlowchart(code) && (
          <button className={btn} onClick={() => setFlow(!flow)} aria-label={flow ? 'Pause flow' : 'Animate flow'} data-tip={flow ? 'Pause flowing connections' : 'Animate connections'}>
            {flow ? <Pause size={15} /> : <Play size={15} />}
          </button>
        )}
        {isFlowchart(code) && (
          <button className="rounded px-1.5 py-1 text-xs text-paper-dim hover:bg-ink-600 hover:text-paper" onClick={() => setEngine(engine === 'elk' ? 'dagre' : 'elk')}
            data-tip={engine === 'elk' ? 'Layout: Smart (right-angle lines that avoid boxes). Click for Classic curves.' : 'Layout: Classic curves. Click for Smart routing.'}>
            {engine === 'elk' ? 'Smart' : 'Classic'}
          </button>
        )}
        <CopyBtn text={code} className="p-1.5" />
        <button className={btn} onClick={download} aria-label="Download SVG" data-tip="Download as SVG image" disabled={!svg}><Download size={15} /></button>
        <button className={btn} onClick={() => setFull(!full)} aria-label={full ? 'Exit full screen' : 'Full screen'} data-tip={full ? 'Exit full screen (Esc)' : 'Full screen'}>
          {full ? <Minimize2 size={15} /> : <Maximize2 size={15} />}
        </button>
      </div>
      <div
        ref={box}
        className={`relative overflow-hidden rounded-md bg-ink-800/40 ${full ? 'flex-1' : ''} ${drag.current ? 'cursor-grabbing' : 'cursor-grab'}`}
        style={{ height }}
        onKeyDown={(e) => e.key === 'Escape' && setFull(false)}
        tabIndex={0}
        aria-label={`${title ?? 'Diagram'}. Drag to move, use the buttons or Ctrl + scroll to zoom.`}
        onPointerDown={(e) => {
          if ((e.target as HTMLElement).closest('button')) return
          drag.current = { x: e.clientX, y: e.clientY, vx: view.x, vy: view.y }
          ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
        }}
        onPointerMove={(e) => {
          const d = drag.current
          if (d) setView((v) => ({ ...v, x: d.vx + e.clientX - d.x, y: d.vy + e.clientY - d.y }))
        }}
        onPointerUp={() => { drag.current = null }}
      >
        {svg ? (
          <div
            ref={stage}
            key={replay}
            className={`mermaid-wrap absolute left-0 top-0 origin-top-left ${flow && !reduced ? 'rx-flow' : ''}`}
            style={{ transform: `translate(${view.x}px, ${view.y}px) scale(${view.s})` }}
            dangerouslySetInnerHTML={{ __html: svg }}
          />
        ) : (
          <div className="m-4 h-40 animate-pulse rounded-md bg-ink-600/40" />
        )}
      </div>
      <p className="mt-2 text-xs text-paper-mute">
        Drag to move · Ctrl + scroll or the buttons to zoom{isFlowchart(code) ? ' · hover a box to highlight its connections' : ''}{full ? ' · Esc to exit' : ''}
      </p>
    </div>
  )
  return full ? createPortal(body, document.body) : body
}

/** Staged entrance: nodes pop in, then edges draw themselves, then labels fade in. */
function animate(root: SVGSVGElement) {
  const nodes = [...root.querySelectorAll<SVGGElement>('g.node, g.mindmap-node, g.cluster, rect.actor, text.actor')]
  nodes.forEach((n, i) => {
    n.classList.add('rx-fade-in')   // opacity only: Mermaid positions nodes with the transform attribute
    n.style.animationDelay = `${Math.min(i * 45, 1200)}ms`
  })
  const nodeTime = Math.min(nodes.length * 45, 1200)

  const edges = [...root.querySelectorAll<SVGPathElement>('path.flowchart-link')]
  edges.forEach((p, i) => {
    p.setAttribute('pathLength', '1')
    p.classList.add('rx-drawing')
    p.style.animationDelay = `${nodeTime * 0.6 + Math.min(i * 40, 1000)}ms`
    p.addEventListener('animationend', () => {
      p.removeAttribute('pathLength')
      p.classList.remove('rx-drawing'); p.classList.add('rx-drawn')
      p.style.animationDelay = ''
    }, { once: true })
  })
  root.querySelectorAll<SVGGElement>('.edgeLabel').forEach((l) => {
    l.classList.add('rx-fade-in'); l.style.animationDelay = `${nodeTime + 500}ms`
  })

  // sequence diagrams: reveal messages one by one, like a story
  const lines = [...root.querySelectorAll<SVGElement>('.messageLine0, .messageLine1')]
  const texts = [...root.querySelectorAll<SVGElement>('.messageText')]
  const nums = [...root.querySelectorAll<SVGElement>('.sequenceNumber')]
  lines.forEach((l, i) => {
    const delay = 400 + i * 380
    l.setAttribute('pathLength', '1')
    l.classList.add('rx-drawing'); l.style.animationDelay = `${delay}ms`
    l.addEventListener('animationend', () => { l.removeAttribute('pathLength'); l.classList.remove('rx-drawing') }, { once: true })
    for (const t of [texts[i], nums[i]]) if (t) { t.classList.add('rx-fade-in'); t.style.animationDelay = `${delay + 250}ms` }
  })
}

/** Hovering a flowchart node highlights it, its edges and its direct neighbours. */
function wireHover(root: SVGSVGElement) {
  const nodeEls = [...root.querySelectorAll<SVGGElement>('g.node')]
  if (!nodeEls.length) return
  const idOf = (el: Element) => (el.id.match(/flowchart-(.+)-\d+$/) || [])[1]
  const ids = new Set<string>([...nodeEls.map(idOf).filter(Boolean), ...[...root.querySelectorAll('g.cluster')].map((c) => c.id.replace(/^.*?-(?=L_)/, ''))])
  const edges = [...root.querySelectorAll<SVGPathElement>('path.flowchart-link')].map((p) => {
    const raw = (p.getAttribute('data-id') || p.id.replace(/^.*?-(?=L_)/, '')).replace(/^L_/, '').replace(/_\d+$/, '')
    for (const a of ids) {
      if (raw.startsWith(a + '_') && ids.has(raw.slice(a.length + 1))) return { p, a, b: raw.slice(a.length + 1) }
    }
    return { p, a: '', b: '' }
  })
  const byId = new Map(nodeEls.map((n) => [idOf(n), n]))
  const clear = () => {
    root.classList.remove('rx-dim')
    root.querySelectorAll('.rx-hot').forEach((e) => e.classList.remove('rx-hot'))
  }
  const enter = (n: SVGGElement) => {
    const id = idOf(n)
    clear()
    root.classList.add('rx-dim')
    n.classList.add('rx-hot')
    for (const e of edges) {
      if (e.a === id || e.b === id) {
        e.p.classList.add('rx-hot')
        byId.get(e.a === id ? e.b : e.a)?.classList.add('rx-hot')
      }
    }
  }
  const handlers = nodeEls.map((n) => {
    const on = () => enter(n)
    n.addEventListener('mouseenter', on); n.addEventListener('mouseleave', clear)
    return () => { n.removeEventListener('mouseenter', on); n.removeEventListener('mouseleave', clear) }
  })
  return () => handlers.forEach((h) => h())
}
