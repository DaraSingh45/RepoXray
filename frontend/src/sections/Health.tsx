import { PolarAngleAxis, PolarGrid, Radar, RadarChart, ResponsiveContainer } from 'recharts'
import { CheckCircle2, ShieldAlert, XCircle } from 'lucide-react'
import { Result } from '../lib/api'
import { Bar, Panel, Section, Tag } from '../components/ui'
import type { OpenFile } from '../pages/Analysis'

export default function Health({ r, openFile }: { r: Result; openFile: OpenFile }) {
  const q = r.quality
  const all = [...(r.insights.improvements ?? []).map((i) => ({ ...i, ai: true })), ...q.improvements.map((i) => ({ ...i, ai: false }))]
  const order = { high: 0, medium: 1, low: 2 } as Record<string, number>
  all.sort((a, b) => (order[a.priority?.toLowerCase()] ?? 3) - (order[b.priority?.toLowerCase()] ?? 3))
  const sev = { high: r.security.filter((s) => s.severity === 'high').length, medium: r.security.filter((s) => s.severity === 'medium').length }

  return (
    <Section title="Health & improvements" lede={`Score ${q.score}/100 (grade ${q.grade}), weighted across ${q.checks.length} checks. Fixing the high-priority items below raises the score the most.`}>
      <div className="grid gap-6 xl:grid-cols-[1fr_380px]">
        <Panel title="Recommended improvements">
          {all.length === 0 ? <p className="text-sm text-paper-mute">No issues found. This repository passes every check.</p> : (
            <ul className="divide-y divide-ink-500">
              {all.map((i, k) => (
                <li key={k} className="flex gap-3 py-3 first:pt-0">
                  <div className="w-16 shrink-0 pt-0.5"><Tag tone={i.priority?.toLowerCase()}>{i.priority || 'idea'}</Tag></div>
                  <div className="min-w-0">
                    <div className="font-medium text-paper">{i.title}</div>
                    <p className="text-sm text-paper-dim">{i.detail}</p>
                    <div className="mt-1 text-xs text-paper-mute">{i.category}{i.ai ? ' · suggested by AI' : ''}</div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Panel>
        <div className="space-y-6">
          <Panel title="Score by area">
            <ResponsiveContainer width="100%" height={230}>
              <RadarChart data={q.categories} outerRadius="72%">
                <PolarGrid stroke="#24364F" />
                <PolarAngleAxis dataKey="name" tick={{ fill: '#C9D5E3', fontSize: 12 }} />
                <Radar dataKey="score" stroke="#4FC3C7" strokeWidth={2} fill="#4FC3C7" fillOpacity={0.28} animationDuration={1000} dot={{ r: 3, fill: '#8FE3E6' }} />
              </RadarChart>
            </ResponsiveContainer>
            <ul className="mt-2 space-y-2.5">
              {q.categories.map((c) => (
                <li key={c.name}>
                  <div className="mb-1 flex justify-between text-sm"><span className="text-paper-dim">{c.name}</span><span className="tabular-nums text-paper-mute">{c.score} · {c.passed}/{c.total}</span></div>
                  <Bar value={c.score} />
                </li>
              ))}
            </ul>
          </Panel>
        </div>
      </div>

      <Panel title="All checks">
        <div className="grid gap-x-8 gap-y-2 md:grid-cols-2">
          {q.checks.map((c) => (
            <div key={c.name} className="flex items-start gap-2 text-sm" data-tip={c.passed ? undefined : `How to fix: ${c.fix}`}>
              {c.passed ? <CheckCircle2 size={15} className="mt-0.5 shrink-0 text-ok" /> : <XCircle size={15} className={`mt-0.5 shrink-0 ${c.score > 0.5 ? 'text-warn' : 'text-bad'}`} />}
              <span className={c.passed ? 'text-paper-dim' : 'text-paper'}>{c.name}</span>
              <span className="ml-auto shrink-0 text-xs text-paper-mute" data-tip={c.passed ? undefined : c.fix}>{c.category}</span>
            </div>
          ))}
        </div>
      </Panel>

      <div className="grid gap-6 xl:grid-cols-2">
        <Panel title="Complexity hotspots" aside={<span className="text-xs text-paper-mute">branching × recent changes</span>}>
          {q.hotspots.length === 0 ? <p className="text-sm text-paper-mute">No source files.</p> : (
            <table className="table-base">
              <thead><tr><th>File</th><th className="text-right" data-tip="Lines of code">LOC</th><th className="text-right" data-tip="Approximate number of branches (if, loops, cases) plus functions">Complexity</th><th className="text-right" data-tip="How many recent commits changed this file">Changes</th></tr></thead>
              <tbody>{q.hotspots.slice(0, 10).map((h) => (
                <tr key={h.path}>
                  <td><button onClick={() => openFile(h.path)} data-tip={h.path} className="path block max-w-[260px] truncate text-left text-xs hover:underline">{h.path}</button></td>
                  <td className="text-right tabular-nums text-paper-dim">{h.lines}</td>
                  <td className="text-right tabular-nums"><span className={h.complexity > 60 ? 'text-bad' : h.complexity > 30 ? 'text-warn' : 'text-paper-dim'}>{h.complexity}</span></td>
                  <td className="text-right tabular-nums text-paper-dim">{h.churn || '—'}</td>
                </tr>
              ))}</tbody>
            </table>
          )}
        </Panel>
        <Panel title="Security findings" aside={<ShieldAlert size={16} className={sev.high ? 'text-bad' : 'text-paper-mute'} />}>
          {r.security.length === 0 ? <p className="text-sm text-paper-mute">No leaked secrets or risky patterns found by the scanner. This is a pattern scan, not a full security audit.</p> : (
            <ul className="space-y-2.5">
              {r.security.slice(0, 30).map((s, i) => (
                <li key={i} className="flex gap-3 text-sm">
                  <div className="w-16 shrink-0"><Tag tone={s.severity}>{s.severity}</Tag></div>
                  <div className="min-w-0">
                    <div className="text-paper">{s.type}</div>
                    <button onClick={() => openFile(s.file, s.line || undefined)} className="path text-xs hover:underline">{s.file}{s.line ? `:${s.line}` : ''}</button>
                    {s.detail && <div className="truncate font-mono text-2xs text-paper-mute" data-tip={s.detail}>{s.detail}</div>}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>

      {r.todos.length > 0 && (
        <Panel title={`TODO and FIXME notes (${r.todos.length})`}>
          <ul className="space-y-1.5 text-sm">
            {r.todos.slice(0, 40).map((t, i) => (
              <li key={i} className="flex gap-3">
                <span className={`w-12 shrink-0 font-mono text-2xs ${t.kind === 'FIXME' || t.kind === 'BUG' ? 'text-bad' : 'text-warn'}`}>{t.kind}</span>
                <span className="min-w-0 flex-1 truncate text-paper-dim" data-tip={t.text && t.text.length > 60 ? t.text : undefined}>{t.text || '(no description)'}</span>
                <button onClick={() => openFile(t.path, t.line)} data-tip={`${t.path}:${t.line}`} className="path shrink-0 text-xs hover:underline">{t.path.split('/').pop()}:{t.line}</button>
              </li>
            ))}
          </ul>
        </Panel>
      )}
    </Section>
  )
}
