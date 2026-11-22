import { useEffect, useMemo, useState } from 'react'
import { ChevronDown, ChevronRight, FileCode2, Folder, FolderOpen, Search, Sparkles, X } from 'lucide-react'
import { ResponsiveContainer, Treemap } from 'recharts'
import { api, fmt, Result, Symbol, TreeNode } from '../lib/api'
import CodeView from '../components/CodeView'
import Markdown from '../components/Markdown'
import { Section, Spinner } from '../components/ui'
import type { OpenFile } from '../pages/Analysis'

export default function Files({ id, r, path, line, openFile }: { id: string; r: Result; path: string | null; line?: number; openFile: OpenFile }) {
  const [q, setQ] = useState('')
  const [view, setView] = useState<'tree' | 'treemap'>('tree')
  const langColor = useMemo(() => Object.fromEntries(r.languages.map((l) => [l.name, l.color])), [r])

  const matches = useMemo(() => {
    if (!q.trim()) return []
    const s = q.toLowerCase()
    return r.files.filter((f) => f.path.toLowerCase().includes(s)).slice(0, 60)
  }, [q, r.files])

  return (
    <Section title="Files & code" lede={`${fmt.n(r.metrics.files)} files in ${fmt.n(r.metrics.dirs)} folders, ${fmt.bytes(r.metrics.size_bytes)} in total. Open any file to read it with highlighting, see its symbols, and get an explanation.`}
      actions={
        <div className="flex rounded-md border border-ink-500 p-0.5 text-sm">
          {(['tree', 'treemap'] as const).map((v) => (
            <button key={v} onClick={() => setView(v)} aria-pressed={view === v} className={`rounded px-3 py-1 ${view === v ? 'bg-ink-600 text-paper' : 'text-paper-mute'}`}>{v === 'tree' ? 'Explorer' : 'Size map'}</button>
          ))}
        </div>
      }>
      {view === 'treemap' ? <SizeMap tree={r.tree} colors={langColor} onPick={(p) => { setView('tree'); openFile(p) }} /> : (
        <div className="grid gap-4 lg:grid-cols-[320px_1fr]">
          <div className="panel flex max-h-[760px] flex-col overflow-hidden">
            <div className="relative border-b border-ink-500 p-2">
              <Search size={14} className="absolute left-4 top-1/2 -translate-y-1/2 text-paper-mute" />
              <input className="input pl-8" placeholder="Filter files" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Filter files" />
            </div>
            <div className="flex-1 overflow-auto py-1 text-[0.82rem]">
              {q.trim() ? (
                matches.length === 0 ? <p className="p-3 text-paper-mute">No files match “{q}”.</p> :
                matches.map((f) => (
                  <button key={f.path} onClick={() => openFile(f.path)} data-tip={f.path.length > 40 ? f.path : undefined} className={`block w-full truncate px-3 py-1 text-left font-mono text-xs hover:bg-ink-600 ${f.path === path ? 'text-contour' : 'text-paper-dim'}`}>{f.path}</button>
                ))
              ) : <Tree node={r.tree} depth={0} current={path} onPick={openFile} colors={langColor} />}
            </div>
          </div>
          <FilePane id={id} r={r} path={path} line={line} />
        </div>
      )}
    </Section>
  )
}

function Tree({ node, depth, current, onPick, colors }: { node: TreeNode; depth: number; current: string | null; onPick: OpenFile; colors: Record<string, string> }) {
  const [open, setOpen] = useState(depth < 1 || (!!current && current.startsWith(node.path + '/')))
  // files sit one indent step deeper than their folder's chevron
  depth = node.type === 'file' ? depth - 0.4 : depth
  useEffect(() => { if (current && current.startsWith(node.path + '/')) setOpen(true) }, [current, node.path])
  if (node.type === 'file') {
    return (
      <button onClick={() => onPick(node.path)} style={{ paddingLeft: depth * 12 + 10 }}
        className={`flex w-full items-center gap-1.5 py-[3px] pr-2 text-left hover:bg-ink-600 ${current === node.path ? 'bg-ink-600 text-paper' : 'text-paper-dim'}`}>
        <span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: colors[node.language ?? ''] ?? '#34496A' }} />
        <span className="truncate" data-tip={node.name.length > 30 ? node.path : undefined}>{node.name}</span>
        {node.lines > 0 && <span className="ml-auto text-2xs tabular-nums text-paper-mute">{node.lines}</span>}
      </button>
    )
  }
  if (depth === 0) return <>{node.children?.map((c) => <Tree key={c.path} node={c} depth={1} current={current} onPick={onPick} colors={colors} />)}</>
  return (
    <div>
      <button onClick={() => setOpen(!open)} style={{ paddingLeft: depth * 12 - 2 }} aria-expanded={open}
        className="flex w-full items-center gap-1 py-[3px] pr-2 text-left text-paper hover:bg-ink-600">
        {open ? <ChevronDown size={13} className="text-paper-mute" /> : <ChevronRight size={13} className="text-paper-mute" />}
        {open ? <FolderOpen size={14} className="text-survey" /> : <Folder size={14} className="text-survey" />}
        <span className="truncate">{node.name}</span>
        <span className="ml-auto text-2xs text-paper-mute">{node.files}</span>
      </button>
      {open && node.children?.map((c) => <Tree key={c.path} node={c} depth={depth + 1} current={current} onPick={onPick} colors={colors} />)}
    </div>
  )
}

function FilePane({ id, r, path, line }: { id: string; r: Result; path: string | null; line?: number }) {
  const [file, setFile] = useState<{ content: string; symbols: Symbol[]; language: string | null } | null>(null)
  const [err, setErr] = useState('')
  const [hl, setHl] = useState<number | undefined>(line)
  const [explain, setExplain] = useState<{ md: string; src: string } | null>(null)
  const [explaining, setExplaining] = useState(false)

  useEffect(() => {
    setFile(null); setErr(''); setExplain(null); setHl(line)
    if (!path) return
    api.file(id, path).then(setFile).catch((e) => setErr(e.message))
  }, [id, path, line])

  if (!path) {
    const start = r.entry_points[0]?.path || r.readme_path
    return (
      <div className="panel grid min-h-[400px] place-items-center p-8 text-center">
        <div>
          <FileCode2 size={30} className="mx-auto text-paper-mute" />
          <p className="mt-3 text-paper">Pick a file from the explorer.</p>
          {start && <p className="mt-1 text-sm text-paper-mute">A good place to start is <span className="path">{start}</span>.</p>}
        </div>
      </div>
    )
  }
  const meta = r.files.find((f) => f.path === path)
  const runExplain = async () => {
    setExplaining(true)
    try { const x = await api.explain(id, path); setExplain({ md: x.markdown, src: x.source }) } catch (e: any) { setExplain({ md: `Could not explain this file: ${e.message}`, src: 'error' }) }
    setExplaining(false)
  }

  return (
    <div className="panel flex max-h-[760px] min-w-0 flex-col overflow-hidden">
      <div className="flex flex-wrap items-center gap-3 border-b border-ink-500 px-4 py-2.5">
        <span className="path truncate" data-tip={path}>{path}</span>
        {meta && <span className="text-xs text-paper-mute">{meta.language ?? 'text'} · {fmt.n(meta.lines)} loc · used by {meta.in} · uses {meta.out}</span>}
        <button className="btn-outline ml-auto py-1 text-xs" onClick={runExplain} disabled={explaining || !file}>
          {explaining ? <Spinner size={12} /> : <Sparkles size={13} />} Explain this file
        </button>
      </div>
      {explain && (
        <div className="relative max-h-[45%] overflow-auto border-b border-ink-500 bg-ink-800 px-5 py-3">
          <button className="absolute right-3 top-3 text-paper-mute hover:text-paper" onClick={() => setExplain(null)} aria-label="Close explanation" data-tip="Close"><X size={15} /></button>
          <Markdown>{explain.md}</Markdown>
        </div>
      )}
      <div className="flex min-h-0 flex-1">
        <div className="min-w-0 flex-1 bg-ink-900">
          {err ? <p className="p-5 text-sm text-paper-mute">{err === 'Binary file' ? 'This is a binary file and cannot be previewed.' : err}</p>
            : !file ? <div className="p-5"><Spinner /></div>
            : <CodeView code={file.content} language={file.language} highlight={hl} />}
        </div>
        {file && file.symbols.length > 0 && (
          <div className="hidden w-52 shrink-0 overflow-auto border-l border-ink-500 p-3 xl:block">
            <div className="mb-2 text-xs text-paper-mute">Outline</div>
            <ul className="space-y-0.5">
              {file.symbols.map((s) => (
                <li key={s.name + s.line}>
                  <button onClick={() => setHl(s.line)} data-tip={`${s.kind} ${s.name}, line ${s.line}${s.doc ? `\n${s.doc}` : ''}`} className="flex w-full items-center gap-1.5 truncate rounded px-1.5 py-0.5 text-left text-xs text-paper-dim hover:bg-ink-600">
                    <span className={`font-mono text-2xs ${s.kind === 'class' || s.kind === 'type' ? 'text-survey' : 'text-contour'}`}>{s.kind === 'class' ? 'C' : s.kind === 'type' ? 'T' : s.kind === 'const' ? 'k' : 'ƒ'}</span>
                    <span className="truncate">{s.name}</span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  )
}

function SizeMap({ tree, colors, onPick }: { tree: TreeNode; colors: Record<string, string>; onPick: (p: string) => void }) {
  const data = useMemo(() => {
    const dominant = (n: TreeNode): string | null => {
      const acc: Record<string, number> = {}
      const walk = (x: TreeNode) => {
        if (x.type === 'file') { if (x.language) acc[x.language] = (acc[x.language] ?? 0) + Math.max(1, x.lines) }
        else x.children?.forEach(walk)
      }
      walk(n)
      return Object.entries(acc).sort((a, b) => b[1] - a[1])[0]?.[0] ?? null
    }
    const conv = (n: TreeNode, d: number): any => {
      if (n.type === 'file') return { name: n.name, path: n.path, size: Math.max(1, n.lines), color: colors[n.language ?? ''] ?? '#34496A' }
      if (d > 3) return { name: n.name + '/', path: n.path, size: Math.max(1, n.lines), color: colors[dominant(n) ?? ''] ?? '#34496A', dir: true }
      const kids = (n.children ?? []).map((c) => conv(c, d + 1)).filter((c) => c.size > 0 || c.children?.length)
      return { name: n.name, path: n.path, children: kids }
    }
    return (tree.children ?? []).map((c) => conv(c, 1)).filter((c) => (c.size ?? 1) > 0)
  }, [tree, colors])
  return (
    <div className="panel rx-enter p-3">
      <p className="mb-3 px-2 text-sm text-paper-mute">Area shows lines of code; colour shows language. Click a file to open it.</p>
      <ResponsiveContainer width="100%" height={620}>
        <Treemap data={data} dataKey="size" stroke="#0F1B2D" isAnimationActive={false}
          content={<Cell onPick={onPick} /> as any} />
      </ResponsiveContainer>
    </div>
  )
}

function Cell(props: any) {
  const { x, y, width, height, name, color, path, depth, onPick, children, dir } = props
  if (width < 2 || height < 2) return null
  const leaf = !children
  return (
    <g onClick={() => leaf && !dir && path && onPick(path)} style={{ cursor: leaf && !dir ? 'pointer' : 'default' }} data-tip={leaf ? `${path}${props.size ? `\n${props.size.toLocaleString()} lines` : ''}` : undefined}>
      <rect x={x} y={y} width={width} height={height} fill={leaf ? color : 'transparent'} fillOpacity={leaf ? 0.6 : 0} stroke="#0F1B2D" strokeWidth={depth === 1 ? 3 : 1}
        className={leaf ? 'transition-[fill-opacity] duration-150 hover:[fill-opacity:0.95]' : ''} />
      {leaf && width > 60 && height > 18 && <text x={x + 5} y={y + 14} fontSize={11.5} fill="#FFFFFF" style={{ paintOrder: 'stroke', stroke: '#0F1B2D', strokeWidth: 3 }}>{String(name).slice(0, Math.floor(width / 7))}</text>}
      {!leaf && depth === 1 && width > 50 && <text x={x + 5} y={y + 15} fontSize={12.5} fontWeight={600} fill="#F5B86E" style={{ paintOrder: 'stroke', stroke: '#0F1B2D', strokeWidth: 3 }}>{name}</text>}
    </g>
  )
}
