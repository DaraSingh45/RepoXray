import { FormEvent, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { AlertCircle, Bot, Loader2, Trash2 } from 'lucide-react'
import Contours from '../components/Contours'
import { AnalysisRow, api, fmt, LLMSettings } from '../lib/api'

const EXAMPLES = [
  { url: 'https://github.com/fastapi/full-stack-fastapi-template', label: 'FastAPI + React template' },
  { url: 'https://github.com/expressjs/express', label: 'Express' },
  { url: 'https://github.com/karpathy/nanoGPT', label: 'nanoGPT' },
  { url: 'https://github.com/spring-projects/spring-petclinic', label: 'Spring PetClinic' },
]

const WHAT_YOU_GET = [
  ['Architecture map', 'Modules, layers and how they depend on each other, as an interactive graph.'],
  ['Flowcharts', 'Execution path from the entry point, request lifecycle, and how to build and run it.'],
  ['Stack & dependencies', 'Frameworks, databases and tooling, with outdated packages flagged.'],
  ['Health report', 'A score across docs, tests, CI, security and maintenance, with concrete fixes.'],
  ['Ask the code', 'Chat with the repository. Answers cite the files they come from.'],
]

export default function Home() {
  const nav = useNavigate()
  const [url, setUrl] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [rows, setRows] = useState<AnalysisRow[] | null>(null)
  const [llm, setLlm] = useState<LLMSettings | null>(null)

  const load = () => api.list().then(setRows).catch(() => setRows([]))
  useEffect(() => {
    load()
    api.getLLM().then(setLlm).catch(() => {})
    const t = setInterval(load, 4000)
    return () => clearInterval(t)
  }, [])

  const submit = async (e?: FormEvent, value?: string, force = false) => {
    e?.preventDefault()
    const target = (value ?? url).trim()
    if (!target) { setErr('Paste a GitHub repository URL, for example github.com/owner/repo.'); return }
    setBusy(true); setErr('')
    try {
      const r = await api.analyze(target, force)
      nav(`/a/${r.id}`)
    } catch (ex: any) {
      setErr(ex.message)
    } finally { setBusy(false) }
  }

  return (
    <div>
      <section className="relative overflow-hidden border-b border-ink-500">
        <Contours />
        <div className="relative mx-auto max-w-3xl px-5 pb-20 pt-24">
          <h1 className="text-[2.6rem] sm:text-[3.4rem] font-semibold leading-[1.05] tracking-tight">
            Understand any GitHub repository in minutes.
          </h1>
          <p className="mt-5 max-w-[60ch] text-lg text-paper-dim leading-relaxed">
            Paste a link. RepoXray reads the code, maps its architecture, draws its flows, scores its health and
            answers your questions about it, even when the project is unfinished or out of date.
          </p>
          <form onSubmit={submit} className="mt-9">
            <label htmlFor="repo" className="sr-only">GitHub repository URL</label>
            <div className="flex flex-col gap-2 sm:flex-row rounded-xl border border-ink-400 bg-ink-900/80 p-2 focus-within:border-contour">
              <input
                id="repo" autoFocus value={url} onChange={(e) => setUrl(e.target.value)}
                placeholder="https://github.com/owner/repository"
                className="flex-1 bg-transparent px-3 py-2.5 font-mono text-[0.95rem] text-paper placeholder:text-paper-mute focus:outline-none"
              />
              <button className="btn-primary justify-center px-5 py-2.5" disabled={busy}>
                {busy ? <Loader2 size={16} className="animate-spin" /> : null} Map repository
              </button>
            </div>
            {err && <p className="mt-3 flex items-center gap-2 text-sm text-bad"><AlertCircle size={15} /> {err}</p>}
          </form>
          <div className="mt-5 flex flex-wrap items-center gap-2 text-sm text-paper-mute">
            <span>Try</span>
            {EXAMPLES.map((ex) => (
              <button key={ex.url} onClick={() => { setUrl(ex.url); submit(undefined, ex.url) }} className="chip hover:border-contour hover:text-paper">
                {ex.label}
              </button>
            ))}
          </div>
          {llm && (
            <p className="mt-8 flex items-center gap-2 text-sm text-paper-mute">
              <Bot size={15} />
              {llm.provider === 'none'
                ? <>AI is off. Analyses use static analysis only. <Link to="/settings" className="text-contour hover:underline">Connect Ollama or an API</Link></>
                : <>AI insights by <span className="text-paper-dim">{llm.provider} / {llm.model}</span>. <Link to="/settings" className="text-contour hover:underline">Change</Link></>}
            </p>
          )}
        </div>
      </section>

      <div className="mx-auto grid max-w-[1200px] gap-12 px-5 py-14 lg:grid-cols-[1fr_380px]">
        <section>
          <h2 className="h-section mb-5">Your analyses</h2>
          {rows === null ? (
            <div className="space-y-2">{[0, 1, 2].map((i) => <div key={i} className="h-16 animate-pulse rounded-lg bg-ink-700" />)}</div>
          ) : rows.length === 0 ? (
            <p className="text-paper-mute">Nothing mapped yet. Paste a repository link above to create your first map.</p>
          ) : (
            <ul className="divide-y divide-ink-500 border-y border-ink-500">
              {rows.map((r) => (
                <li key={r.id} className="group flex items-center gap-4 py-3.5">
                  <Grade score={r.score} status={r.status} />
                  <Link to={`/a/${r.id}`} className="min-w-0 flex-1">
                    <div className="truncate font-medium text-paper group-hover:text-contour-glow">{r.owner}/{r.repo}</div>
                    <div className="truncate text-sm text-paper-mute" data-tip={r.status === 'failed' ? r.error ?? undefined : undefined}>
                      {r.status === 'failed' ? <span className="text-bad">{r.error}</span>
                        : r.status !== 'done' ? `Analysing… ${Math.round(r.progress)}%`
                        : r.description || r.language || 'Analysis complete'}
                    </div>
                  </Link>
                  <span className="hidden text-xs text-paper-mute sm:block">{fmt.ago(r.created_at)}</span>
                  <button
                    className="rounded p-1.5 text-paper-mute opacity-60 hover:text-bad group-hover:opacity-100 focus:opacity-100"
                    aria-label={`Delete analysis of ${r.repo}`} data-tip="Delete this analysis"
                    onClick={async () => { if (confirm(`Delete the analysis of ${r.owner}/${r.repo}?`)) { await api.remove(r.id); load() } }}
                  >
                    <Trash2 size={15} />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>
        <aside>
          <h2 className="h-section mb-5">What you get</h2>
          <dl className="space-y-4">
            {WHAT_YOU_GET.map(([t, d]) => (
              <div key={t} className="border-l-2 border-ink-400 pl-4">
                <dt className="font-medium text-paper">{t}</dt>
                <dd className="text-sm text-paper-mute leading-relaxed">{d}</dd>
              </div>
            ))}
          </dl>
        </aside>
      </div>
    </div>
  )
}

function Grade({ score, status }: { score?: number | null; status: string }) {
  if (status === 'failed') return <div className="grid h-10 w-10 place-items-center rounded-full border border-bad/40 text-bad"><AlertCircle size={16} /></div>
  if (status !== 'done' || score == null) return <div className="grid h-10 w-10 place-items-center rounded-full border border-ink-400"><Loader2 size={16} className="animate-spin text-contour" /></div>
  const c = score >= 75 ? '#6CCB8B' : score >= 55 ? '#F0A04B' : '#EF6F6C'
  return <div className="grid h-10 w-10 place-items-center rounded-full border-2 text-sm font-semibold tabular-nums" style={{ borderColor: c, color: c }}>{score}</div>
}
