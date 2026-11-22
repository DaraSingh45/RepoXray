import { lazy, Suspense, useCallback, useEffect, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import {
  Activity, AlertTriangle, Boxes, CheckCircle2, Circle, CircleDashed, Code2, Download, ExternalLink, FileJson, FolderTree,
  GitBranch, HeartPulse, Layers, LayoutDashboard, Loader2, MessagesSquare, Network, Package, RefreshCw, Route, Star, Workflow, XCircle,
} from 'lucide-react'
import { Analysis as A, api, fmt, Step } from '../lib/api'
import { Spinner } from '../components/ui'
import Overview from '../sections/Overview'
import Stack from '../sections/Stack'
import Files from '../sections/Files'
import ApiRoutes from '../sections/ApiRoutes'
import Dependencies from '../sections/Dependencies'
import Health from '../sections/Health'
import ActivitySection from '../sections/Activity'
import Ask from '../sections/Ask'

const ArchitectureMap = lazy(() => import('../sections/ArchitectureMap'))
const Flows = lazy(() => import('../sections/Flows'))

export const SECTIONS = [
  { key: 'overview', label: 'Overview', icon: LayoutDashboard },
  { key: 'map', label: 'Architecture map', icon: Network },
  { key: 'flows', label: 'Flowcharts', icon: Workflow },
  { key: 'stack', label: 'Tech stack', icon: Layers },
  { key: 'files', label: 'Files & code', icon: FolderTree },
  { key: 'api', label: 'API routes', icon: Route },
  { key: 'deps', label: 'Dependencies', icon: Package },
  { key: 'health', label: 'Health & improvements', icon: HeartPulse },
  { key: 'activity', label: 'Activity', icon: Activity },
  { key: 'ask', label: 'Ask the code', icon: MessagesSquare },
] as const
export type SectionKey = (typeof SECTIONS)[number]['key']

export default function Analysis() {
  const { id = '' } = useParams()
  const [params, setParams] = useSearchParams()
  const [a, setA] = useState<A | null>(null)
  const [err, setErr] = useState('')
  const section = (params.get('s') as SectionKey) || 'overview'

  const load = useCallback(() => api.get(id).then((x) => { setA(x); setErr('') }).catch((e) => setErr(e.message)), [id])
  useEffect(() => { setA(null); load() }, [load])

  // poll while running, or while AI insights are regenerating
  const running = a && (a.status === 'queued' || a.status === 'running' || a.result?.regenerating)
  useEffect(() => {
    if (!running) return
    const t = setInterval(load, 1200)
    return () => clearInterval(t)
  }, [running, load])

  const go = (s: SectionKey, extra: Record<string, string> = {}) => {
    setParams({ s, ...extra })
    window.scrollTo({ top: 0 })
  }
  const openFile = (path: string, line?: number) => go('files', { f: path, ...(line ? { l: String(line) } : {}) })

  if (err) return <div className="mx-auto max-w-xl p-10"><p className="text-bad">{err}</p><Link to="/" className="text-contour">Back to analyses</Link></div>
  if (!a) return <div className="grid h-[60vh] place-items-center"><Spinner size={28} /></div>

  const r = a.result
  if (!r) return <Progress a={a} />

  return (
    <div className="mx-auto flex max-w-[1500px] gap-8 px-5">
      <aside className="sticky top-14 hidden h-[calc(100vh-3.5rem)] w-56 shrink-0 overflow-y-auto py-8 lg:block">
        <nav className="space-y-0.5" aria-label="Analysis sections">
          {SECTIONS.map(({ key, label, icon: Icon }) => (
            <button
              key={key} onClick={() => go(key)}
              className={`flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-left text-sm ${section === key ? 'bg-ink-600 text-paper' : 'text-paper-mute hover:text-paper hover:bg-ink-700'}`}
              aria-current={section === key ? 'page' : undefined}
            >
              <Icon size={16} className={section === key ? 'text-contour' : ''} /> {label}
            </button>
          ))}
        </nav>
        <div className="mt-8 space-y-1 border-t border-ink-500 pt-5 text-sm">
          <a className="btn-ghost w-full" data-tip="Download a shareable Markdown summary" href={`/api/analyses/${id}/report.md`}><Download size={15} /> Markdown report</a>
          <a className="btn-ghost w-full" data-tip="Download every detail as JSON" href={`/api/analyses/${id}/report.json`}><FileJson size={15} /> Raw JSON</a>
        </div>
      </aside>

      <div className="min-w-0 flex-1 py-8">
        <Header a={a} onReanalyze={async () => { const x = await api.analyze(a.url, true); window.location.href = `/a/${x.id}` }} />
        {a.status !== 'done' && <InlineProgress steps={a.steps} />}
        <div className="mb-6 flex gap-1 overflow-x-auto lg:hidden">
          {SECTIONS.map(({ key, label }) => (
            <button key={key} onClick={() => go(key)} className={`chip whitespace-nowrap ${section === key ? 'border-contour text-paper' : ''}`}>{label}</button>
          ))}
        </div>
        <div key={section} className="rx-enter">
        <Suspense fallback={<div className="h-96 animate-pulse rounded-lg bg-ink-700" />}>
          {section === 'overview' && <Overview a={a} go={go} openFile={openFile} reload={load} />}
          {section === 'map' && <ArchitectureMap r={r} openFile={openFile} />}
          {section === 'flows' && <Flows r={r} />}
          {section === 'stack' && <Stack r={r} />}
          {section === 'files' && <Files id={id} r={r} path={params.get('f')} line={Number(params.get('l')) || undefined} openFile={openFile} />}
          {section === 'api' && <ApiRoutes r={r} openFile={openFile} />}
          {section === 'deps' && <Dependencies r={r} />}
          {section === 'health' && <Health r={r} openFile={openFile} />}
          {section === 'activity' && <ActivitySection r={r} />}
          {section === 'ask' && <Ask id={id} r={r} openFile={openFile} ready={!!r.rag} />}
        </Suspense>
        </div>
      </div>
    </div>
  )
}

function Header({ a, onReanalyze }: { a: A; onReanalyze: () => void }) {
  const r = a.result!
  const m = r.meta
  return (
    <header className="mb-8 flex flex-wrap items-start justify-between gap-5 border-b border-ink-500 pb-6">
      <div className="flex min-w-0 items-start gap-4">
        {m.avatar ? <img src={m.avatar} alt="" className="h-12 w-12 rounded-lg" /> : <div className="grid h-12 w-12 place-items-center rounded-lg bg-ink-600"><Boxes size={22} className="text-contour" /></div>}
        <div className="min-w-0">
          <h1 className="truncate text-2xl font-semibold tracking-tight">
            <span className="text-paper-mute font-normal">{a.owner} / </span>{a.repo}
          </h1>
          <div className="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-paper-mute">
            <span>{r.project_type}</span>
            {r.fetch.branch && <span className="flex items-center gap-1"><GitBranch size={13} />{r.fetch.branch}</span>}
            {m.stars != null && <span className="flex items-center gap-1"><Star size={13} />{fmt.n(m.stars)}</span>}
            {m.license && <span>{m.license}</span>}
            {r.subpath && <span className="path">/{r.subpath}</span>}
            {m.archived && <span className="text-warn">Archived</span>}
            <a href={r.url} target="_blank" rel="noreferrer" className="flex items-center gap-1 hover:text-contour">GitHub <ExternalLink size={12} /></a>
          </div>
        </div>
      </div>
      <button className="btn-outline" data-tip="Fetch the latest code and analyse again" onClick={onReanalyze}><RefreshCw size={14} /> Re-analyse</button>
    </header>
  )
}

function StepIcon({ s }: { s: Step['status'] }) {
  if (s === 'done') return <CheckCircle2 size={17} className="text-ok" />
  if (s === 'running') return <Loader2 size={17} className="animate-spin text-contour" />
  if (s === 'failed') return <XCircle size={17} className="text-bad" />
  if (s === 'skipped') return <CircleDashed size={17} className="text-paper-mute" />
  return <Circle size={17} className="text-ink-400" />
}

function Progress({ a }: { a: A }) {
  const failed = a.status === 'failed'
  return (
    <div className="mx-auto max-w-2xl px-5 py-16">
      <p className="text-sm text-paper-mute">{failed ? 'Analysis failed' : 'Mapping repository'}</p>
      <h1 className="mt-1 text-3xl font-semibold tracking-tight">{a.owner}/{a.repo}</h1>
      {!failed && (
        <div className="mt-6 h-1.5 overflow-hidden rounded-full bg-ink-600">
          <div className="h-full bg-contour transition-all duration-700" style={{ width: `${Math.max(3, a.progress)}%` }} />
        </div>
      )}
      {failed && (
        <div className="mt-6 rounded-lg border border-bad/40 bg-bad/5 p-4 text-sm">
          <div className="flex items-center gap-2 font-medium text-bad"><AlertTriangle size={16} /> {a.error}</div>
          <Link to="/" className="mt-3 inline-block text-contour hover:underline">Try another repository</Link>
        </div>
      )}
      <ol className="mt-8 space-y-3.5">
        {a.steps.length === 0 && <li className="text-paper-mute">Waiting in queue…</li>}
        {a.steps.map((s) => (
          <li key={s.key} className="flex items-start gap-3">
            <StepIcon s={s.status} />
            <div className="min-w-0">
              <div className={s.status === 'pending' ? 'text-paper-mute' : 'text-paper'}>{s.label}</div>
              {s.detail && <div className="truncate text-xs text-paper-mute">{s.detail}</div>}
            </div>
            {s.ms > 0 && <span className="ml-auto text-xs tabular-nums text-paper-mute">{(s.ms / 1000).toFixed(1)}s</span>}
          </li>
        ))}
      </ol>
    </div>
  )
}

function InlineProgress({ steps }: { steps: Step[] }) {
  const cur = steps.find((s) => s.status === 'running')
  return (
    <div className="mb-6 flex items-center gap-3 rounded-lg border border-contour/30 bg-contour/5 px-4 py-3 text-sm">
      <Loader2 size={16} className="animate-spin text-contour" />
      <span>Results are ready to browse. Still working on: <span className="text-paper">{cur?.label ?? 'finishing up'}</span>{cur?.detail ? ` (${cur.detail})` : ''}</span>
    </div>
  )
}

export type Go = (s: SectionKey, extra?: Record<string, string>) => void
export type OpenFile = (path: string, line?: number) => void
export { Code2 }
