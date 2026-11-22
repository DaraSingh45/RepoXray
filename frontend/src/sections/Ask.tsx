import { FormEvent, useEffect, useRef, useState } from 'react'
import { ArrowUp, Bot, FileCode2, Square, Trash2 } from 'lucide-react'
import { chatStream, Result } from '../lib/api'
import Markdown from '../components/Markdown'
import { Section, Spinner } from '../components/ui'
import type { OpenFile } from '../pages/Analysis'

type Msg = { role: 'user' | 'assistant'; content: string; sources?: { path: string; start: number; end: number }[]; pending?: boolean }

function suggestions(r: Result) {
  const s = ['What does this project do, and how is it structured?', 'Walk me through what happens when the app starts.']
  if (r.routes.length) s.push(`How is the ${r.routes[0].method.split(',')[0]} ${r.routes[0].path} endpoint handled?`)
  if (r.stack.some((t) => t.category === 'Database' || t.category === 'ORM')) s.push('How does the app store and query data?')
  if (r.stack.some((t) => t.category === 'Auth')) s.push('How does authentication work?')
  s.push('Where should I start if I want to add a new feature?')
  return s.slice(0, 5)
}

export default function Ask({ id, r, openFile, ready }: { id: string; r: Result; openFile: OpenFile; ready: boolean }) {
  const key = `repoxray-chat-${id}`
  const [msgs, setMsgs] = useState<Msg[]>(() => { try { return JSON.parse(sessionStorage.getItem(key) || '[]') } catch { return [] } })
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const abort = useRef<AbortController | null>(null)
  const end = useRef<HTMLDivElement>(null)

  useEffect(() => { try { sessionStorage.setItem(key, JSON.stringify(msgs.filter((m) => !m.pending))) } catch { /* storage unavailable */ } }, [msgs, key])
  useEffect(() => { end.current?.scrollIntoView({ block: 'end' }) }, [msgs])

  const send = async (e?: FormEvent, text?: string) => {
    e?.preventDefault()
    const q = (text ?? input).trim()
    if (!q || busy) return
    setInput('')
    const history = msgs.map(({ role, content }) => ({ role, content }))
    setMsgs((m) => [...m, { role: 'user', content: q }, { role: 'assistant', content: '', pending: true }])
    setBusy(true)
    abort.current = new AbortController()
    const patch = (fn: (m: Msg) => Msg) => setMsgs((all) => { const c = [...all]; c[c.length - 1] = fn(c[c.length - 1]); return c })
    try {
      for await (const ev of chatStream(id, q, history, abort.current.signal)) {
        if (ev.type === 'sources') patch((m) => ({ ...m, sources: ev.data }))
        else if (ev.type === 'token') patch((m) => ({ ...m, content: m.content + ev.data }))
      }
    } catch (err: any) {
      if (err.name !== 'AbortError') patch((m) => ({ ...m, content: m.content + `\n\nThe answer could not be completed: ${err.message}` }))
    } finally {
      patch((m) => ({ ...m, pending: false }))
      setBusy(false)
    }
  }

  return (
    <Section title="Ask the code" lede={<>Questions are answered from the repository’s own files using retrieval-augmented generation. {r.rag?.note && <span className="text-paper-mute">Search: {r.rag.note}.</span>}</>}
      actions={msgs.length > 0 && <button className="btn-ghost text-sm" onClick={() => setMsgs([])}><Trash2 size={14} /> Clear conversation</button>}>
      {!ready ? <div className="panel flex items-center gap-3 p-5 text-sm text-paper-dim"><Spinner /> The knowledge index is still being built. Chat opens when it is ready.</div> : (
        <div className="panel flex h-[calc(100vh-15rem)] min-h-[520px] flex-col">
          <div className="flex-1 space-y-6 overflow-y-auto p-5">
            {msgs.length === 0 && (
              <div className="mx-auto max-w-xl pt-6">
                <p className="text-paper">Ask anything about <span className="font-medium">{r.repo}</span>.</p>
                <div className="mt-4 space-y-2">
                  {suggestions(r).map((s) => (
                    <button key={s} onClick={() => send(undefined, s)} className="block w-full rounded-md border border-ink-500 px-4 py-2.5 text-left text-sm text-paper-dim hover:border-contour hover:text-paper">{s}</button>
                  ))}
                </div>
              </div>
            )}
            {msgs.map((m, i) => m.role === 'user' ? (
              <div key={i} className="flex justify-end"><div className="max-w-[75%] rounded-lg bg-ink-600 px-4 py-2.5 text-paper">{m.content}</div></div>
            ) : (
              <div key={i} className="flex gap-3">
                <div className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-contour/15"><Bot size={15} className="text-contour" /></div>
                <div className="min-w-0 flex-1">
                  {m.content ? <Markdown onPath={openFile}>{m.content}</Markdown> : m.pending && <div className="pt-1"><Spinner /></div>}
                  {m.sources && m.sources.length > 0 && (
                    <div className="mt-3 flex flex-wrap gap-1.5">
                      {m.sources.map((s, k) => (
                        <button key={k} onClick={() => openFile(s.path, s.start)} data-tip={`Open ${s.path}, lines ${s.start}–${s.end}`} className="chip hover:border-contour hover:text-paper">
                          <FileCode2 size={12} /><span className="font-mono text-2xs">{s.path.split('/').slice(-2).join('/')}:{s.start}</span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}
            <div ref={end} />
          </div>
          <form onSubmit={send} className="border-t border-ink-500 p-3">
            <div className="flex items-end gap-2 rounded-lg border border-ink-500 bg-ink-900 p-1.5 focus-within:border-contour">
              <textarea
                value={input} onChange={(e) => setInput(e.target.value)} rows={1} placeholder="Ask about the code, e.g. “where is the database configured?”"
                onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
                className="max-h-40 flex-1 resize-none bg-transparent px-2 py-1.5 text-sm text-paper placeholder:text-paper-mute focus:outline-none" aria-label="Your question"
              />
              {busy
                ? <button type="button" onClick={() => abort.current?.abort()} className="btn-outline px-2.5 py-1.5" aria-label="Stop answer" data-tip="Stop"><Square size={14} /></button>
                : <button className="btn-primary px-2.5 py-1.5" disabled={!input.trim()} aria-label="Send question" data-tip="Send (Enter)"><ArrowUp size={16} /></button>}
            </div>
          </form>
        </div>
      )}
    </Section>
  )
}
