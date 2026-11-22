import { useEffect, useState } from 'react'
import { Bot, Loader2, Sparkles, Terminal } from 'lucide-react'
import { Analysis, api, fmt, LLMSettings } from '../lib/api'
import { CopyBtn, Panel, Stat, Tag } from '../components/ui'
import { useCountUp } from '../lib/motion'
import type { Go, OpenFile } from '../pages/Analysis'

const CMD_LABEL: Record<string, string> = { install: 'Install', build: 'Build', test: 'Test', run: 'Run', docker: 'Docker' }

export default function Overview({ a, go, openFile, reload }: { a: Analysis; go: Go; openFile: OpenFile; reload: () => void }) {
  const r = a.result!
  const ins = r.insights
  const m = r.metrics
  const [llm, setLlm] = useState<LLMSettings | null>(null)
  const [regenErr, setRegenErr] = useState('')
  useEffect(() => { api.getLLM().then(setLlm).catch(() => {}) }, [])
  const codeLangs = r.languages.filter((l) => l.is_code)
  const totalBytes = codeLangs.reduce((s, l) => s + l.bytes, 0) || 1
  const cmds = (['install', 'build', 'test', 'run', 'docker'] as const).filter((k) => r.commands[k]?.length)

  const regenerate = async () => {
    setRegenErr('')
    try { await api.regenerate(a.id); reload() } catch (e: any) { setRegenErr(e.message) }
  }

  return (
    <div className="space-y-8">
      {/* Summary + score */}
      <div className="grid gap-6 xl:grid-cols-[1fr_260px]">
        <div>
          <p className="text-[1.15rem] leading-relaxed text-paper max-w-[72ch]">{ins.summary}</p>
          {ins.purpose && ins.purpose !== ins.summary && (
            <p className="mt-4 text-paper-dim max-w-[72ch]"><span className="text-paper font-medium">Purpose. </span>{ins.purpose}</p>
          )}
          {ins.audience && <p className="mt-2 text-paper-dim"><span className="text-paper font-medium">For. </span>{ins.audience}</p>}
          <div className="mt-4 flex flex-wrap items-center gap-3 text-xs text-paper-mute">
            {ins.source === 'llm'
              ? <span className="flex items-center gap-1.5"><Sparkles size={13} className="text-contour" /> Written by {ins.model}</span>
              : <span className="flex items-center gap-1.5"><Bot size={13} /> Generated from static analysis</span>}
            {r.regenerating && <span className="flex items-center gap-1.5 text-contour"><Loader2 size={13} className="animate-spin" /> Generating AI insights…</span>}
            {!r.regenerating && llm && llm.provider !== 'none' && a.status === 'done' && (
              <button onClick={regenerate} className="text-contour hover:underline">{ins.source === 'llm' ? 'Regenerate with AI' : 'Generate AI insights'}</button>
            )}
            {ins.llm_error && <span className="text-warn">AI unavailable: {ins.llm_error}</span>}
            {regenErr && <span className="text-bad">{regenErr}</span>}
          </div>
        </div>
        <button onClick={() => go('health')} className="panel flex items-center gap-5 p-5 text-left hover:border-ink-400">
          <ScoreRing score={r.quality.score} />
          <div>
            <div className="text-sm text-paper-mute">Health grade</div>
            <div className="text-3xl font-semibold">{r.quality.grade}</div>
            <div className="text-xs text-contour mt-1">{r.quality.improvements.length} improvements</div>
          </div>
        </button>
      </div>

      {/* Key numbers */}
      <div className="panel grid grid-cols-2 gap-6 p-5 sm:grid-cols-3 xl:grid-cols-6">
        <Stat value={fmt.n(m.source_loc)} label="lines of code" hint="Non-blank, non-comment source lines (tests excluded)" />
        <Stat value={fmt.n(m.source_files)} label="source files" />
        <Stat value={fmt.n(m.test_files)} label="test files" />
        <Stat value={r.stack.length} label="technologies" />
        <Stat value={r.routes.length} label="API routes" />
        <Stat value={r.git.available ? fmt.n(r.git.commit_count) : '—'} label="commits" hint={r.git.shallow ? 'Recent history sampled' : undefined} />
      </div>

      {/* Language bar */}
      {codeLangs.length > 0 && (
        <div>
          <div className="rx-reveal flex h-3 overflow-hidden rounded-full">
            {codeLangs.map((l) => <div key={l.name} style={{ width: `${(l.bytes / totalBytes) * 100}%`, background: l.color }} data-tip={`${l.name}: ${l.percent}% of code`} />)}
          </div>
          <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1.5 text-sm">
            {codeLangs.slice(0, 8).map((l) => (
              <span key={l.name} className="flex items-center gap-1.5 text-paper-dim">
                <span className="h-2.5 w-2.5 rounded-full" style={{ background: l.color }} />{l.name}
                <span className="text-paper-mute tabular-nums">{((l.bytes / totalBytes) * 100).toFixed(1)}%</span>
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="grid items-start gap-6 xl:grid-cols-2">
        <Panel title="How it works">
          <ol className="space-y-4">
            {ins.how_it_works.map((s, i) => (
              <li key={i} className="flex gap-3.5">
                <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full border border-contour/50 text-xs text-contour tabular-nums">{i + 1}</span>
                <div>
                  <div className="font-medium text-paper">{s.step}</div>
                  <InlineCode text={s.detail} openFile={openFile} />
                </div>
              </li>
            ))}
          </ol>
          {ins.architecture && <p className="mt-5 border-t border-ink-500 pt-4 text-sm text-paper-dim leading-relaxed">{ins.architecture}</p>}
          <button onClick={() => go('map')} className="mt-4 text-sm text-contour hover:underline">Open the architecture map</button>
        </Panel>

        <Panel title="Get it running" aside={<Terminal size={16} className="text-paper-mute" />}>
          {cmds.length === 0 && !r.commands.from_readme?.length ? (
            <p className="text-sm text-paper-mute">No build or run commands could be inferred. Check the README for setup instructions.</p>
          ) : (
            <div className="space-y-3">
              {cmds.map((k) => (
                <div key={k}>
                  <div className="mb-1 text-xs text-paper-mute">{CMD_LABEL[k]}</div>
                  {r.commands[k].slice(0, 2).map((c) => <Cmd key={c} c={c} />)}
                </div>
              ))}
              {r.commands.from_readme?.length > 0 && (
                <details className="pt-1">
                  <summary className="cursor-pointer text-xs text-paper-mute hover:text-paper">Commands mentioned in the README ({r.commands.from_readme.length})</summary>
                  <div className="mt-2">{r.commands.from_readme.map((c) => <Cmd key={c} c={c} />)}</div>
                </details>
              )}
            </div>
          )}
          {r.env_vars.length > 0 && (
            <div className="mt-5 border-t border-ink-500 pt-4">
              <div className="mb-2 text-xs text-paper-mute">Environment variables the code reads ({r.env_vars.length})</div>
              <div className="flex flex-wrap gap-1.5">
                {r.env_vars.slice(0, 24).map((e) => (
                  <span key={e.name} tabIndex={0} data-tip={e.documented ? 'Documented in a .env template' : `Read in ${e.files.join(', ')}. Not in a .env template.`}
                    className={`rounded border px-1.5 py-px font-mono text-2xs ${e.documented ? 'border-ok/30 text-ok' : 'border-ink-400 text-paper-dim'}`}>{e.name}</span>
                ))}
              </div>
            </div>
          )}
        </Panel>
      </div>

      <div className="grid items-start gap-6 xl:grid-cols-3">
        <Panel title="Entry points">
          {r.entry_points.length === 0 ? <p className="text-sm text-paper-mute">No executable entry point found. This is likely a library, collection of scripts, or documentation.</p> : (
            <ul className="space-y-3">
              {r.entry_points.slice(0, 5).map((e) => (
                <li key={e.path}>
                  <button onClick={() => openFile(e.path)} className="path hover:underline text-left break-all">{e.path}</button>
                  <div className="text-xs text-paper-mute">{e.reasons.join('; ')}</div>
                </li>
              ))}
            </ul>
          )}
        </Panel>
        <Panel title="Key components">
          <ul className="space-y-3">
            {ins.key_components.slice(0, 7).map((k, i) => (
              <li key={i}>
                <div className="flex items-baseline gap-2">
                  <span className="font-medium text-paper">{k.name}</span>
                </div>
                {k.path && <button onClick={() => openFile(k.path)} className="path text-left text-xs hover:underline break-all">{k.path}</button>}
                <div className="text-xs text-paper-mute">{k.role}</div>
              </li>
            ))}
          </ul>
        </Panel>
        <Panel title="Suggested reading order">
          <ol className="space-y-3">
            {ins.learning_path.map((s, i) => (
              <li key={i} className="flex gap-3">
                <span className="text-xs text-paper-mute tabular-nums pt-0.5">{i + 1}.</span>
                <div className="min-w-0">
                  <button onClick={() => openFile(s.path)} className="path text-left hover:underline break-all">{s.path}</button>
                  <div className="text-xs text-paper-mute">{s.why}</div>
                </div>
              </li>
            ))}
          </ol>
        </Panel>
      </div>

      {(ins.use_cases.length > 0 || (r.readme.features?.length ?? 0) > 0 || (r.meta.topics?.length ?? 0) > 0) && (
        <Panel title="Use cases and features">
          <ul className="grid gap-x-8 gap-y-2 text-sm text-paper-dim sm:grid-cols-2">
            {(ins.use_cases.length ? ins.use_cases : r.readme.features ?? []).map((u, i) => <li key={i} className="border-l-2 border-ink-400 pl-3">{u}</li>)}
          </ul>
          {r.meta.topics && r.meta.topics.length > 0 && <div className="mt-4 flex flex-wrap gap-1.5">{r.meta.topics.map((t) => <Tag key={t}>{t}</Tag>)}</div>}
        </Panel>
      )}

      {(ins.improvements?.length ?? 0) > 0 && (
        <Panel title="AI-suggested improvements" aside={<button onClick={() => go('health')} className="text-sm text-contour hover:underline">All improvements</button>}>
          <ul className="space-y-3">
            {ins.improvements.slice(0, 5).map((i, k) => (
              <li key={k} className="flex items-start gap-3">
                <Tag tone={i.priority?.toLowerCase()}>{i.priority || 'idea'}</Tag>
                <div><div className="font-medium text-paper">{i.title}</div><InlineCode text={i.detail} openFile={openFile} /></div>
              </li>
            ))}
          </ul>
        </Panel>
      )}
      {r.fetch.note && <p className="text-xs text-paper-mute">{r.fetch.note}</p>}
      {m.truncated && <p className="text-xs text-warn">Large repository: {fmt.n(m.files)} of {fmt.n(m.total_files)} files were analysed in detail.</p>}
    </div>
  )
}

function Cmd({ c }: { c: string }) {
  return (
    <div className="group mb-1 flex items-center justify-between gap-2 rounded-md bg-ink-900 px-3 py-1.5 font-mono text-[0.8rem] text-paper">
      <span className="truncate" data-tip={c.length > 60 ? c : undefined}><span className="text-paper-mute select-none">$ </span>{c}</span>
      <CopyBtn text={c} className="opacity-60 group-hover:opacity-100 focus:opacity-100" />
    </div>
  )
}

export function InlineCode({ text, openFile }: { text: string; openFile: OpenFile }) {
  const parts = text.split(/(`[^`]+`)/g)
  return (
    <p className="text-sm text-paper-dim leading-relaxed">
      {parts.map((p, i) => {
        if (!p.startsWith('`')) return <span key={i}>{p}</span>
        const v = p.slice(1, -1)
        const looksPath = /[./]/.test(v) && !v.includes(' ')
        return looksPath
          ? <button key={i} onClick={() => openFile(v.split(':')[0])} className="path hover:underline">{v}</button>
          : <code key={i} className="font-mono text-[0.8rem] text-contour-glow">{v}</code>
      })}
    </p>
  )
}

function ScoreRing({ score }: { score: number }) {
  const c = score >= 75 ? '#6CCB8B' : score >= 55 ? '#F0A04B' : '#EF6F6C'
  const R = 30, C = 2 * Math.PI * R
  const shown = useCountUp(score, 1200)
  return (
    <svg width="76" height="76" viewBox="0 0 76 76" aria-label={`Health score ${score} of 100`}>
      <circle cx="38" cy="38" r={R} fill="none" stroke="#24364F" strokeWidth="7" />
      <circle cx="38" cy="38" r={R} fill="none" stroke={c} strokeWidth="7" strokeLinecap="round" strokeDasharray={`${(shown / 100) * C} ${C}`} transform="rotate(-90 38 38)" />
      <text x="38" y="43" textAnchor="middle" fontSize="17" fontWeight="600" fill="#E7EEF6">{Math.round(shown)}</text>
    </svg>
  )
}
