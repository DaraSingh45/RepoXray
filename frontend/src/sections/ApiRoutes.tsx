import { useMemo, useState } from 'react'
import { Result } from '../lib/api'
import { Empty, Section, Tag } from '../components/ui'
import type { OpenFile } from '../pages/Analysis'

export default function ApiRoutes({ r, openFile }: { r: Result; openFile: OpenFile }) {
  const [q, setQ] = useState('')
  const [method, setMethod] = useState('ALL')
  const methods = useMemo(() => ['ALL', ...Array.from(new Set(r.routes.map((x) => x.method.split(',')[0])))], [r])
  const rows = r.routes.filter((x) => (method === 'ALL' || x.method.startsWith(method)) && (x.path + x.file).toLowerCase().includes(q.toLowerCase()))
  const byFile = useMemo(() => {
    const m = new Map<string, number>()
    r.routes.forEach((x) => m.set(x.file, (m.get(x.file) ?? 0) + 1))
    return [...m.entries()].sort((a, b) => b[1] - a[1])
  }, [r])

  return (
    <Section title="API routes" lede="HTTP endpoints found in route decorators and router calls (FastAPI, Flask, Django, Express, NestJS, Spring, Gin, Rails, Laravel, ASP.NET, Next.js).">
      {r.routes.length === 0 ? <Empty title="No HTTP routes found">This project does not appear to expose a web API, or it defines routes in a way RepoXray does not recognise.</Empty> : (
        <div className="grid gap-6 xl:grid-cols-[1fr_280px]">
          <div>
            <div className="mb-3 flex flex-wrap gap-2">
              <input className="input max-w-xs" placeholder="Filter by path or file" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Filter routes" />
              <div className="flex flex-wrap gap-1">{methods.map((m) => (
                <button key={m} onClick={() => setMethod(m)} aria-pressed={method === m} className={`chip ${method === m ? 'border-contour text-paper' : ''}`}>{m}</button>
              ))}</div>
            </div>
            <div className="panel overflow-x-auto">
              <table className="table-base">
                <thead><tr><th className="w-24">Method</th><th>Path</th><th>Defined in</th></tr></thead>
                <tbody>
                  {rows.map((x, i) => (
                    <tr key={i}>
                      <td><Tag tone={x.method.split(',')[0]}>{x.method}</Tag></td>
                      <td className="font-mono text-[0.8rem] text-paper">{x.path}</td>
                      <td><button onClick={() => openFile(x.file, x.line)} className="path text-xs hover:underline">{x.file}:{x.line}</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {rows.length === 0 && <p className="p-4 text-sm text-paper-mute">No routes match the filter.</p>}
            </div>
          </div>
          <div>
            <h3 className="h-block mb-3">Routes per file</h3>
            <ul className="space-y-2">
              {byFile.slice(0, 15).map(([f, n]) => (
                <li key={f} className="flex items-center justify-between gap-2 text-sm">
                  <button onClick={() => openFile(f)} data-tip={f} className="path truncate text-xs hover:underline">{f}</button>
                  <span className="tabular-nums text-paper-mute">{n}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </Section>
  )
}
