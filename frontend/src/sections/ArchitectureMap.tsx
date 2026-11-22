import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import {
  Background, BackgroundVariant, Controls, Edge, EdgeProps, Handle, Node, NodeProps, Position, ReactFlow,
  ReactFlowProvider, useReactFlow,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import dagre from '@dagrejs/dagre'
import { Maximize2, Minimize2, Pause, Play, X } from 'lucide-react'
import { Result } from '../lib/api'
import { Empty, LAYER_COLORS, Section } from '../components/ui'
import { useReducedMotion } from '../lib/motion'
import type { OpenFile } from '../pages/Analysis'

type Mode = 'modules' | 'files'
type Dir = 'TB' | 'LR'
type Pt = { x: number; y: number }
type NData = { label: string; full: string; sub: string; color: string; w: number; delay: number }
type EData = { path: string; color: string; width: number; tip: string; flow: boolean; entered: boolean; delay: number; weak: boolean; src: string; tgt: string }

const markerId = (c: string) => `rx-arrow-${c.replace('#', '')}`

const NODE_H = 58

// ---------------------------------------------------------------- nodes & edges

// Hover highlighting is done with CSS classes on these elements (like the flowcharts), never by
// re-rendering, so nothing restarts or flickers. The outer "shell" gets the dim/highlight classes;
// the inner box owns the one-time entrance animation.
const MapNode = memo(({ id, data }: NodeProps<Node<NData>>) => (
  <div className="rx-node-shell" data-node-id={id} data-tip={`${data.full}\n${data.sub}\nHover to trace · click to pin`}>
    <div
      className="rx-map-node rounded-md border bg-ink-700 px-3 text-left"
      style={{
        width: data.w, height: NODE_H, display: 'flex', flexDirection: 'column', justifyContent: 'center',
        borderColor: data.color, boxShadow: `inset 4px 0 0 ${data.color}`, animationDelay: `${data.delay}ms`,
        ['--c' as any]: data.color,
      }}
    >
      <Handle type="target" position={Position.Top} className="!h-1 !w-1 !min-h-0 !min-w-0 !border-0 !bg-transparent" />
      <div className="truncate text-[14px] font-semibold text-paper">{data.label}</div>
      <div className="truncate text-[12px] text-paper-dim">{data.sub}</div>
      <Handle type="source" position={Position.Bottom} className="!h-1 !w-1 !min-h-0 !min-w-0 !border-0 !bg-transparent" />
    </div>
  </div>
))

/** Edge drawn through the bend points computed by dagre, so it routes around boxes. */
function RoutedEdge({ id, data }: EdgeProps<Edge<EData>>) {
  const d = data!
  const cls = !d.entered ? 'rx-drawing' : d.flow ? 'rx-flowing' : ''
  return (
    <g className={`rx-edge ${d.weak ? 'rx-weak' : ''}`} data-source={d.src} data-target={d.tgt}>
      {/* wide invisible stroke = easy hover target + tooltip */}
      <path d={d.path} fill="none" stroke="transparent" strokeWidth={16} data-tip={d.tip} style={{ pointerEvents: 'stroke' }} />
      <path
        id={id} d={d.path} fill="none" stroke={d.color} strokeWidth={d.width} markerEnd={`url(#${markerId(d.color)})`}
        className={`rx-edge-line ${cls}`}
        pathLength={!d.entered ? 1 : undefined}
        style={{ ['--w' as any]: `${d.width}px`, animationDelay: !d.entered ? `${d.delay}ms` : undefined }}
      />
    </g>
  )
}

function fallbackPath(a?: Pt, b?: Pt, w = 200, dir: Dir = 'TB') {
  if (!a || !b) return ''
  const s = dir === 'TB' ? { x: a.x + w / 2, y: a.y + NODE_H } : { x: a.x + w, y: a.y + NODE_H / 2 }
  const t = dir === 'TB' ? { x: b.x + w / 2, y: b.y } : { x: b.x, y: b.y + NODE_H / 2 }
  const m = dir === 'TB' ? { x: (s.x + t.x) / 2, y: (s.y + t.y) / 2 } : { x: (s.x + t.x) / 2, y: (s.y + t.y) / 2 }
  return dir === 'TB'
    ? `M${s.x},${s.y} C${s.x},${m.y} ${t.x},${m.y} ${t.x},${t.y}`
    : `M${s.x},${s.y} C${m.x},${s.y} ${m.x},${t.y} ${t.x},${t.y}`
}

const nodeTypes = { map: MapNode }
const edgeTypes = { routed: RoutedEdge }

// ---------------------------------------------------------------- layout

function curve(pts: Pt[]) {
  if (pts.length < 2) return ''
  let d = `M${pts[0].x},${pts[0].y}`
  if (pts.length === 2) return `${d} L${pts[1].x},${pts[1].y}`
  for (let i = 0; i < pts.length - 1; i++) {   // Catmull-Rom -> cubic Bezier: smooth curve through every bend point
    const p0 = pts[i - 1] ?? pts[i], p1 = pts[i], p2 = pts[i + 1], p3 = pts[i + 2] ?? p2
    d += ` C${p1.x + (p2.x - p0.x) / 6},${p1.y + (p2.y - p0.y) / 6} ${p2.x - (p3.x - p1.x) / 6},${p2.y - (p3.y - p1.y) / 6} ${p2.x},${p2.y}`
  }
  return d
}

function layout(ids: string[], edges: { source: string; target: string }[], dir: Dir, w: number) {
  const g = new dagre.graphlib.Graph({ multigraph: false })
  g.setGraph({ rankdir: dir, nodesep: dir === 'TB' ? 36 : 22, ranksep: dir === 'TB' ? 96 : 120, edgesep: 18, marginx: 30, marginy: 30, ranker: 'network-simplex' })
  g.setDefaultEdgeLabel(() => ({}))
  ids.forEach((id) => g.setNode(id, { width: w, height: NODE_H }))
  edges.forEach((e) => g.setEdge(e.source, e.target))
  dagre.layout(g)
  const pos: Record<string, Pt> = {}
  ids.forEach((id) => { const n = g.node(id); pos[id] = { x: n.x - w / 2, y: n.y - NODE_H / 2 } })
  const paths: Record<string, string> = {}
  edges.forEach((e) => { const ed = g.edge(e.source, e.target); if (ed?.points) paths[`${e.source}->${e.target}`] = curve(ed.points) })
  const gr = g.graph()
  return { pos, paths, width: gr.width ?? 1, height: gr.height ?? 1 }
}

// ---------------------------------------------------------------- graph

function Graph({ r, mode, openFile, full, setFull }: { r: Result; mode: Mode; openFile: OpenFile; full: boolean; setFull: (f: boolean) => void }) {
  const reduced = useReducedMotion()
  const [pinned, setPinned] = useState<string | null>(null)
  const [hidden, setHidden] = useState<Set<string>>(new Set(['Tests', 'Docs & Examples']))
  const [dirPref, setDirPref] = useState<'auto' | Dir>('auto')
  const [limit, setLimit] = useState(40)
  const [flow, setFlow] = useState(true)
  const [showAll, setShowAll] = useState(false)
  const [entered, setEntered] = useState(false)
  const flowApi = useReactFlow()
  const wrap = useRef<HTMLDivElement>(null)
  const hoverRef = useRef<string | null>(null)
  const pinnedRef = useRef<string | null>(null)
  const leaveTimer = useRef<number>()

  const src = useMemo(() => {
    if (mode === 'modules') {
      return {
        nodes: r.modules.nodes.map((n) => ({ id: n.id, label: n.label || n.id, sub: `${n.files} ${n.files === 1 ? 'file' : 'files'} · ${n.lines.toLocaleString()} lines`, layer: n.layer })),
        edges: r.modules.edges,
      }
    }
    const ranked = [...r.file_graph.nodes].sort((a, b) => (b.in + b.out) - (a.in + a.out)).slice(0, limit)
    const keep = new Set(ranked.map((n) => n.id))
    return {
      nodes: ranked.map((n) => ({ id: n.id, label: n.id.split('/').pop()!, sub: `${n.id.split('/').slice(-3, -1).join('/') || '/'} · used by ${n.in}`, layer: n.test ? 'Tests' : n.layer })),
      edges: r.file_graph.edges.filter((e) => keep.has(e.source) && keep.has(e.target)),
    }
  }, [r, mode, limit])

  const visible = useMemo(() => src.nodes.filter((n) => !hidden.has(n.layer)), [src, hidden])
  const visIds = useMemo(() => new Set(visible.map((n) => n.id)), [visible])
  const allEdges = useMemo(() => src.edges.filter((e) => visIds.has(e.source) && visIds.has(e.target) && e.source !== e.target), [src, visIds])
  // Clarity first: by default draw only the strongest links. A focused box still shows ALL of its links.
  const EDGE_CAP = 35
  const strong = useMemo(() => showAll || allEdges.length <= EDGE_CAP ? allEdges
    : [...allEdges].sort((a, b) => b.weight - a.weight).slice(0, EDGE_CAP), [allEdges, showAll])
  const strongSet = useMemo(() => new Set(strong), [strong])
  const width = mode === 'modules' ? 200 : 185

  // choose the direction whose layout fits the box best (bigger readable zoom)
  const lay = useMemo(() => {
    const ids = visible.map((n) => n.id)
    const box = { w: wrap.current?.clientWidth || 1100, h: wrap.current?.clientHeight || 640 }
    const tb = layout(ids, strong, 'TB', width)
    if (dirPref === 'TB') return { ...tb, dir: 'TB' as Dir }
    const lr = layout(ids, strong, 'LR', width)
    if (dirPref === 'LR') return { ...lr, dir: 'LR' as Dir }
    const z = (l: typeof tb) => Math.min(box.w / l.width, box.h / l.height)
    return z(lr) > z(tb) * 1.1 ? { ...lr, dir: 'LR' as Dir } : { ...tb, dir: 'TB' as Dir }
  }, [visible, strong, dirPref, width, full])

  const layerOf = useMemo(() => Object.fromEntries(src.nodes.map((n) => [n.id, n.layer])), [src])

  // entrance order: by rank (top->bottom or left->right)
  const order = useMemo(() => {
    const ids = [...visible.map((n) => n.id)]
    ids.sort((a, b) => lay.dir === 'TB' ? (lay.pos[a].y - lay.pos[b].y) || (lay.pos[a].x - lay.pos[b].x) : (lay.pos[a].x - lay.pos[b].x) || (lay.pos[a].y - lay.pos[b].y))
    return Object.fromEntries(ids.map((id, i) => [id, i]))
  }, [visible, lay])
  const stagger = Math.min(40, 1200 / Math.max(1, visible.length))

  const maxW = Math.max(1, ...allEdges.map((e) => e.weight))
  const nodes: Node<NData>[] = visible.map((n) => ({
    id: n.id, type: 'map', position: lay.pos[n.id] ?? { x: 0, y: 0 }, draggable: false,
    data: {
      label: n.label, full: n.id, sub: n.sub, color: LAYER_COLORS[n.layer] ?? '#8FA1BA', w: width,
      delay: reduced ? 0 : (order[n.id] ?? 0) * stagger,
    },
  }))
  // every link is rendered once; weaker links stay hidden until a box they touch is hovered or pinned
  const edges: Edge<EData>[] = allEdges.map((e, i) => {
    const color = LAYER_COLORS[layerOf[e.source]] ?? '#7F98BC'
    return {
      id: `e${i}-${e.source}-${e.target}`, source: e.source, target: e.target, type: 'routed',
      data: {
        path: lay.paths[`${e.source}->${e.target}`] ?? fallbackPath(lay.pos[e.source], lay.pos[e.target], width, lay.dir), color, width: 1.2 + (e.weight / maxW) * 2.6,
        weak: !strongSet.has(e), src: e.source, tgt: e.target, flow: flow && !reduced, entered: entered || reduced,
        delay: Math.min(visible.length * stagger, 1200) * 0.7 + (order[e.source] ?? 0) * stagger * 0.5,
        tip: mode === 'modules'
          ? `${e.source}\n→ imports ${e.target}\n${e.weight} import${e.weight === 1 ? '' : 's'}`
          : `${e.source.split('/').pop()} imports ${e.target.split('/').pop()}`,
      },
    }
  })

  // replay entrance whenever the drawing changes
  const signature = `${mode}|${lay.dir}|${visible.length}|${limit}|${[...hidden].join()}|${showAll}`
  useEffect(() => {
    setEntered(false)
    const t = setTimeout(() => setEntered(true), Math.min(visible.length * stagger, 1200) * 0.7 + 1300)
    return () => clearTimeout(t)
  }, [signature]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const t = setTimeout(() => flowApi.fitView({ padding: 0.08, duration: reduced ? 0 : 500, minZoom: 0.62, maxZoom: 1.1 }), 60)
    return () => clearTimeout(t)
  }, [signature, full, flowApi, reduced])
  useEffect(() => { setPinned(null); hoverRef.current = null }, [mode])

  // ---- focus = CSS classes only (no React re-render => no restarts, no flicker) -------------
  const applyFocus = useCallback((id: string | null) => {
    const root = wrap.current
    if (!root) return
    root.querySelectorAll('.rx-hot, .rx-focus-node').forEach((el) => el.classList.remove('rx-hot', 'rx-focus-node'))
    root.classList.toggle('rx-dim', !!id)
    if (!id) return
    const q = (v: string) => CSS.escape(v)
    const shell = root.querySelector(`[data-node-id="${q(id)}"]`)
    shell?.classList.add('rx-hot', 'rx-focus-node')
    root.querySelectorAll<SVGGElement>(`.rx-edge[data-source="${q(id)}"], .rx-edge[data-target="${q(id)}"]`).forEach((g) => {
      g.classList.add('rx-hot')
      const other = g.dataset.source === id ? g.dataset.target : g.dataset.source
      if (other) root.querySelector(`[data-node-id="${q(other)}"]`)?.classList.add('rx-hot')
    })
  }, [reduced])
  const currentFocus = () => hoverRef.current ?? pinnedRef.current
  useEffect(() => { pinnedRef.current = pinned; applyFocus(currentFocus()) }, [pinned, applyFocus])
  // re-apply after any redraw (layout change, filters, entrance finishing)
  useEffect(() => { const t = setTimeout(() => applyFocus(currentFocus()), 30); return () => clearTimeout(t) })
  const onEnter = (id: string) => { window.clearTimeout(leaveTimer.current); hoverRef.current = id; applyFocus(id) }
  // small grace period so moving across the gap between two boxes doesn't flash the whole map
  const onLeave = () => {
    window.clearTimeout(leaveTimer.current)
    leaveTimer.current = window.setTimeout(() => { hoverRef.current = null; applyFocus(pinnedRef.current) }, 200)
  }
  useEffect(() => {
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') { setPinned(null); setFull(false) } }
    window.addEventListener('keydown', esc)
    return () => window.removeEventListener('keydown', esc)
  }, [setFull])

  const layers = Array.from(new Set(src.nodes.map((n) => n.layer)))
  const sel = pinned ? src.nodes.find((n) => n.id === pinned) : null
  const out = pinned ? allEdges.filter((e) => e.source === pinned) : []
  const inc = pinned ? allEdges.filter((e) => e.target === pinned) : []
  const markerColors = Array.from(new Set([...Object.values(LAYER_COLORS), '#7F98BC', '#8FA1BA']))
  const modFiles = pinned && mode === 'modules'
    ? r.files.filter((f) => f.code && !f.test && (f.path.startsWith(pinned + '/') || (pinned === '(root)' && !f.path.includes('/')))).sort((a, b) => b.in - a.in).slice(0, 14)
    : []

  const body = (
    <div className={full ? 'fixed inset-0 z-50 flex flex-col bg-ink-900 p-4' : 'relative'}>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        {layers.map((l) => (
          <button key={l} onClick={() => setHidden((h) => { const n = new Set(h); n.has(l) ? n.delete(l) : n.add(l); return n })}
            className={`chip ${hidden.has(l) ? 'opacity-50 line-through' : 'text-paper'}`} aria-pressed={!hidden.has(l)} data-tip={hidden.has(l) ? `Show ${l}` : `Hide ${l}`}>
            <span className="h-2.5 w-2.5 rounded-full" style={{ background: LAYER_COLORS[l] }} />{l}
          </button>
        ))}
        <div className="ml-auto flex flex-wrap items-center gap-1.5">
          {mode === 'files' && (
            <div className="flex rounded-md border border-ink-400 p-0.5 text-xs" role="group" aria-label="Number of files shown">
              {[25, 40, 80, 150].map((n) => (
                <button key={n} onClick={() => setLimit(n)} aria-pressed={limit === n} data-tip={`Show the ${n} most connected files`}
                  className={`rounded px-2 py-0.5 ${limit === n ? 'bg-ink-600 text-paper' : 'text-paper-mute'}`}>{n}</button>
              ))}
            </div>
          )}
          <div className="flex rounded-md border border-ink-400 p-0.5 text-xs" role="group" aria-label="Layout direction">
            {(['auto', 'TB', 'LR'] as const).map((d) => (
              <button key={d} onClick={() => setDirPref(d)} aria-pressed={dirPref === d}
                data-tip={d === 'auto' ? 'Pick the direction that fits best' : d === 'TB' ? 'Top to bottom' : 'Left to right'}
                className={`rounded px-2 py-0.5 ${dirPref === d ? 'bg-ink-600 text-paper' : 'text-paper-mute'}`}>{d === 'auto' ? 'Auto' : d === 'TB' ? '↓' : '→'}</button>
            ))}
          </div>
          {allEdges.length > EDGE_CAP && (
            <button className="chip" onClick={() => setShowAll(!showAll)}
              data-tip={showAll ? 'Show only the strongest links (clearer)' : 'Draw every link (busier)'}>
              {showAll ? `All ${allEdges.length} links` : `Strongest ${EDGE_CAP} of ${allEdges.length} links`}
            </button>
          )}
          {!reduced && (
            <button className="chip" onClick={() => setFlow(!flow)} data-tip={flow ? 'Pause flowing connections' : 'Animate connections'}>
              {flow ? <Pause size={12} /> : <Play size={12} />} Flow
            </button>
          )}
          <button className="chip" onClick={() => setFull(!full)} data-tip={full ? 'Exit full screen (Esc)' : 'Full screen'}>
            {full ? <Minimize2 size={12} /> : <Maximize2 size={12} />} {full ? 'Exit' : 'Full screen'}
          </button>
        </div>
      </div>

      <div ref={wrap} className={`rx-map panel relative overflow-hidden ${full ? 'flex-1' : 'h-[min(720px,calc(100vh-260px))] min-h-[520px]'}`}>
        <svg width="0" height="0" className="absolute" aria-hidden>
          <defs>
            {[...markerColors, '#F0A04B'].map((c) => (
              <marker key={c} id={c === '#F0A04B' ? 'rx-arrow-hot' : markerId(c)} viewBox="0 0 10 10" refX="9" refY="5"
                markerUnits="userSpaceOnUse" markerWidth="13" markerHeight="13" orient="auto-start-reverse">
                <path d="M0,0 L10,5 L0,10 z" fill={c} />
              </marker>
            ))}
          </defs>
        </svg>
        {nodes.length === 0 ? <div className="p-6"><Empty title="Nothing to draw">All layers are hidden, or no code files were found.</Empty></div> : (
          <ReactFlow
            key={signature}
            nodes={nodes} edges={edges} nodeTypes={nodeTypes} edgeTypes={edgeTypes}
            fitView fitViewOptions={{ padding: 0.08, minZoom: 0.62, maxZoom: 1.1 }} minZoom={0.1} maxZoom={2.5}
            nodesDraggable={false} nodesConnectable={false} elementsSelectable={false} proOptions={{ hideAttribution: true }}
            onNodeMouseEnter={(_, n) => onEnter(n.id)} onNodeMouseLeave={onLeave}
            onNodeClick={(_, n) => setPinned(n.id === pinned ? null : n.id)} onPaneClick={() => setPinned(null)}
            onNodeDoubleClick={(_, n) => mode === 'files' && openFile(n.id)}
          >
            <Background variant={BackgroundVariant.Dots} gap={22} size={1.2} color="#2A3F5C" />
            <Controls showInteractive={false} position="bottom-left" />
          </ReactFlow>
        )}

        {sel && (
          <aside className="rx-enter absolute right-3 top-3 z-10 max-h-[calc(100%-24px)] w-80 overflow-y-auto rounded-lg border border-ink-400 bg-ink-800/95 p-4 shadow-xl backdrop-blur">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="text-xs font-medium" style={{ color: LAYER_COLORS[sel.layer] }}>{sel.layer}</div>
                <div className="path break-all">{sel.id}</div>
              </div>
              <button onClick={() => setPinned(null)} className="text-paper-mute hover:text-paper" aria-label="Close details" data-tip="Close (Esc)"><X size={16} /></button>
            </div>
            <p className="mt-1 text-xs text-paper-dim">{sel.sub}</p>
            {mode === 'files' && <button onClick={() => openFile(sel.id)} className="btn-outline mt-3 w-full justify-center text-xs">Open file</button>}
            <EdgeList title={`Depends on (${out.length})`} items={out.map((e) => e.target)} onPick={setPinned} />
            <EdgeList title={`Used by (${inc.length})`} items={inc.map((e) => e.source)} onPick={setPinned} />
            {modFiles.length > 0 && (
              <div className="mt-4">
                <div className="mb-1.5 text-xs text-paper-mute">Main files</div>
                <ul className="space-y-1">{modFiles.map((f) => (
                  <li key={f.path}><button onClick={() => openFile(f.path)} className="path text-left text-xs hover:underline break-all">{f.path.slice(pinned!.length + 1) || f.path}</button></li>
                ))}</ul>
              </div>
            )}
          </aside>
        )}
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-x-6 gap-y-2 text-xs text-paper-dim">
        <span className="flex items-center gap-2">
          <svg width="44" height="10" aria-hidden><line x1="2" y1="5" x2="34" y2="5" stroke="#7F98BC" strokeWidth="2" /><path d="M34 1 L42 5 L34 9 Z" fill="#7F98BC" /></svg>
          A → B means A imports B
        </span>
        <span className="flex items-center gap-2">
          <svg width="34" height="10" aria-hidden><line x1="2" y1="5" x2="32" y2="5" stroke="#7F98BC" strokeWidth="4" /></svg>
          thicker = more imports
        </span>
        <span>line colour = layer of the importing module</span>
        <span>hover a box to trace it · click to pin · Esc to clear</span>
      </div>
    </div>
  )
  // full screen renders at <body> level so no animated parent can trap position:fixed
  return full ? createPortal(body, document.body) : body
}

function EdgeList({ title, items, onPick }: { title: string; items: string[]; onPick: (s: string) => void }) {
  if (!items.length) return null
  return (
    <div className="mt-4">
      <div className="mb-1.5 text-xs text-paper-mute">{title}</div>
      <ul className="space-y-1">{items.slice(0, 12).map((i) => (
        <li key={i}><button onClick={() => onPick(i)} data-tip="Jump to this module" className="text-left text-xs text-paper-dim hover:text-contour break-all">{i}</button></li>
      ))}</ul>
    </div>
  )
}

export default function ArchitectureMap({ r, openFile }: { r: Result; openFile: OpenFile }) {
  const [mode, setMode] = useState<Mode>('modules')
  const [full, setFull] = useState(false)
  const empty = r.modules.nodes.length === 0
  return (
    <Section
      title="Architecture map"
      lede={mode === 'modules'
        ? 'Each box is a module (a folder of code), coloured by its architectural layer. Arrows run from a module to the modules it imports, and route around boxes so they never cross through one.'
        : `The most connected files and the imports between them (${r.file_graph.total_edges} links in total). Double-click a file to open it.`}
      actions={
        <div className="flex rounded-md border border-ink-400 p-0.5 text-sm" role="tablist">
          {(['modules', 'files'] as Mode[]).map((m) => (
            <button key={m} role="tab" aria-selected={mode === m} onClick={() => setMode(m)} className={`rounded px-3 py-1 ${mode === m ? 'bg-ink-600 text-paper' : 'text-paper-mute'}`}>
              {m === 'modules' ? 'Modules' : 'Files'}
            </button>
          ))}
        </div>
      }
    >
      {empty ? <Empty title="No code structure to map">This repository has no source files that RepoXray can parse, so there is nothing to connect. Check the Files section for its contents.</Empty> : (
        <ReactFlowProvider><Graph r={r} mode={mode} openFile={openFile} full={full} setFull={setFull} /></ReactFlowProvider>
      )}
      {!empty && r.modules.edges.length === 0 && (
        <p className="text-sm text-paper-mute">No imports between modules were detected. The modules may be independent, such as separate examples or scripts, or use a language whose imports are not resolved yet.</p>
      )}
    </Section>
  )
}
