import { useEffect, useState } from 'react'
import { AlertTriangle, CheckCircle2, ExternalLink, Loader2, XCircle } from 'lucide-react'
import { api, LLMSettings, Provider } from '../lib/api'

type Info = { id: Provider; name: string; tag: string; help: string; keyUrl?: string; keyHint?: string; embeddings: boolean }

const PROVIDERS: Info[] = [
  { id: 'ollama', name: 'Ollama', tag: 'Local · free · private', embeddings: true,
    help: 'Runs models on your own computer. Install Ollama, then run `ollama pull llama3.1:8b` and `ollama pull nomic-embed-text`. If RepoXray runs in Docker, the Base URL must be `http://host.docker.internal:11434`.' },
  { id: 'groq', name: 'Groq', tag: 'Cloud · free tier · very fast', embeddings: false, keyUrl: 'https://console.groq.com/keys', keyHint: 'gsk_…',
    help: 'Very fast open models (Llama, Qwen and others). The free tier has per-minute limits, so RepoXray sends shorter prompts. Groq has no embeddings, so code search uses keyword matching.' },
  { id: 'gemini', name: 'Google Gemini', tag: 'Cloud · free tier', embeddings: true, keyUrl: 'https://aistudio.google.com/apikey', keyHint: 'AIza…',
    help: 'Google’s Gemini models through their OpenAI-compatible endpoint. Long context and semantic code search with Gemini embeddings.' },
  { id: 'openai', name: 'OpenAI / compatible', tag: 'Cloud · paid', embeddings: true, keyUrl: 'https://platform.openai.com/api-keys', keyHint: 'sk-…',
    help: 'OpenAI, or any other OpenAI-compatible server (OpenRouter, Together, LM Studio, vLLM) by changing the Base URL.' },
  { id: 'anthropic', name: 'Anthropic', tag: 'Cloud · paid', embeddings: false, keyUrl: 'https://console.anthropic.com/settings/keys', keyHint: 'sk-ant-…',
    help: 'Anthropic’s Messages API. Enter a model ID from your console. Code search uses keyword matching.' },
  { id: 'none', name: 'No AI', tag: 'Static analysis only', embeddings: false,
    help: 'Maps, flowcharts, stack, health and keyword code search all still work. Only written explanations and chat answers need a model.' },
]

function Code({ text }: { text: string }) {
  return <>{text.split(/(`[^`]+`)/g).map((t, i) => t.startsWith('`') ? <code key={i} className="font-mono text-[0.8rem] text-paper-dim">{t.slice(1, -1)}</code> : t)}</>
}

export default function Settings() {
  const [s, setS] = useState<LLMSettings | null>(null)
  const [saved, setSaved] = useState<LLMSettings | null>(null)
  const [key, setKey] = useState('')
  const [models, setModels] = useState<{ chat: string[]; embed: string[]; error?: string }>({ chat: [], embed: [] })
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState('')
  const [test, setTest] = useState<null | 'running' | Awaited<ReturnType<typeof api.testLLM>>>(null)
  const [err, setErr] = useState('')

  const loadModels = () => api.models().then((m) => setModels({ chat: m.models, embed: m.embed_models ?? [], error: m.error })).catch(() => setModels({ chat: [], embed: [] }))
  useEffect(() => { api.getLLM().then((x) => { setS(x); setSaved(x); if (x.provider !== 'none') loadModels() }).catch((e) => setErr(e.message)) }, [])

  if (!s || !saved) return <div className="p-10 text-paper-mute">{err || 'Loading settings…'}</div>
  const info = PROVIDERS.find((p) => p.id === s.provider) ?? PROVIDERS[0]
  const needsKey = !['ollama', 'none'].includes(s.provider)
  const keyStatus = saved.keys?.[s.provider] ?? ''
  const isSavedProvider = saved.provider === s.provider
  const modelMissing = isSavedProvider && models.chat.length > 0 && s.model && !models.chat.includes(s.model)

  const pick = (id: Provider) => {
    const prof = saved.profiles?.[id] ?? { base_url: '', model: '', embed_model: '' }
    setS({ ...s, provider: id, ...prof })
    setKey(''); setTest(null); setNote('')
  }

  const save = async () => {
    setBusy(true); setErr(''); setNote('')
    try {
      const out = await api.putLLM({ provider: s.provider, base_url: s.base_url, model: s.model, embed_model: s.embed_model, temperature: s.temperature, ...(key ? { api_key: key } : {}) })
      setS(out); setSaved(out); setKey(''); setNote('Settings saved.')
      if (out.provider !== 'none') await loadModels()
      return out
    } catch (e: any) { setErr(e.message) } finally { setBusy(false) }
  }

  const removeKey = async () => {
    const out = await api.putLLM({ provider: s.provider, clear_api_key: true })
    setS(out); setSaved(out); setNote('Key removed from Settings.')
  }

  const runTest = async () => {
    const out = await save()
    if (!out) return
    setTest('running')
    try { setTest(await api.testLLM()) } catch (e: any) { setTest({ ok: false, message: e.message, models: [], embeddings: false }) }
  }

  return (
    <div className="mx-auto max-w-3xl px-5 py-12">
      <h1 className="text-3xl font-semibold tracking-tight">AI settings</h1>
      <p className="lede mt-2">Choose the model RepoXray uses to explain repositories and answer questions. Keys are stored on your RepoXray server, never in the browser.</p>

      <fieldset className="mt-9">
        <legend className="h-block mb-3">Provider</legend>
        <div className="grid gap-2 sm:grid-cols-3">
          {PROVIDERS.map((p) => {
            const k = saved.keys?.[p.id]
            return (
              <label key={p.id} className={`cursor-pointer rounded-lg border px-4 py-3 ${s.provider === p.id ? 'border-contour bg-contour/5' : 'border-ink-500 hover:border-ink-400'}`}>
                <input type="radio" name="provider" className="sr-only" checked={s.provider === p.id} onChange={() => pick(p.id)} />
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium">{p.name}</span>
                  {saved.provider === p.id && <span className="text-2xs text-contour">active</span>}
                </div>
                <div className="mt-0.5 text-xs text-paper-mute">{p.tag}</div>
                {k && <div className="mt-1 text-2xs text-ok">{k === 'env' ? 'Key from .env' : 'Key saved'}</div>}
              </label>
            )
          })}
        </div>
        <p className="mt-3 text-sm leading-relaxed text-paper-mute"><Code text={info.help} /></p>
      </fieldset>

      {s.provider !== 'none' && (
        <div className="mt-8 space-y-5">
          {needsKey && (
            <Field label="API key" hint={
              keyStatus === 'settings' ? `A key is saved for ${info.name} (${isSavedProvider ? s.api_key : 'hidden'}). Type a new one to replace it.`
              : keyStatus === 'env' ? `Using the key from your .env file. A key typed here overrides it.`
              : `Required. ${info.keyUrl ? 'Create one at the link on the right, then paste it here.' : ''}`}>
              <div className="flex gap-2">
                <input className="input font-mono" type="password" autoComplete="off" value={key} onChange={(e) => setKey(e.target.value)}
                  placeholder={keyStatus ? 'Keep current key' : info.keyHint} aria-label={`${info.name} API key`} />
                {info.keyUrl && <a href={info.keyUrl} target="_blank" rel="noreferrer" className="btn-outline whitespace-nowrap">Get a key <ExternalLink size={13} /></a>}
                {keyStatus === 'settings' && <button type="button" onClick={removeKey} className="btn-ghost whitespace-nowrap">Remove</button>}
              </div>
            </Field>
          )}
          <Field label="Chat model" hint={
            isSavedProvider && models.chat.length ? `${models.chat.length} models available. Start typing to see them.`
            : needsKey && !keyStatus ? 'Save your key first to load the list of available models.'
            : 'Type the model name, or save to load the available models.'}>
            <input className="input font-mono" list="chat-models" value={s.model} onChange={(e) => setS({ ...s, model: e.target.value })} placeholder="model name" />
            <datalist id="chat-models">{(isSavedProvider ? models.chat : []).map((m) => <option key={m} value={m} />)}</datalist>
            {modelMissing && <p className="mt-1.5 flex items-center gap-1.5 text-xs text-warn"><AlertTriangle size={13} /> “{s.model}” isn’t offered by this provider. Pick a model from the list.</p>}
          </Field>
          {info.embeddings && (
            <Field label="Embedding model" hint="Used for semantic code search (RAG). Leave empty to use keyword search only.">
              <input className="input font-mono" list="embed-models" value={s.embed_model} onChange={(e) => setS({ ...s, embed_model: e.target.value })} />
              <datalist id="embed-models">{(isSavedProvider ? models.embed : []).map((m) => <option key={m} value={m} />)}</datalist>
            </Field>
          )}
          <details className="rounded-lg border border-ink-500 px-4 py-3">
            <summary className="cursor-pointer text-sm text-paper-dim">Advanced</summary>
            <div className="mt-4 space-y-5">
              <Field label="Base URL" hint="Where the model API lives. The default is correct unless you use a proxy or a self-hosted server.">
                <input className="input font-mono" value={s.base_url} onChange={(e) => setS({ ...s, base_url: e.target.value })} />
              </Field>
              <Field label={`Temperature: ${s.temperature.toFixed(1)}`} hint="Lower is more factual. 0.2 suits code analysis.">
                <input type="range" min={0} max={1} step={0.1} value={s.temperature} onChange={(e) => setS({ ...s, temperature: Number(e.target.value) })} className="w-full accent-[#4FC3C7]" />
              </Field>
            </div>
          </details>
        </div>
      )}

      <div className="mt-9 flex flex-wrap items-center gap-3">
        <button className="btn-primary" onClick={save} disabled={busy}>{busy && <Loader2 size={15} className="animate-spin" />} Save settings</button>
        {s.provider !== 'none' && <button className="btn-outline" onClick={runTest} disabled={busy || test === 'running'}>{test === 'running' && <Loader2 size={15} className="animate-spin" />} Save and test connection</button>}
        {note && !test && <span className="text-sm text-ok">{note}</span>}
        {err && <span className="text-sm text-bad">{err}</span>}
      </div>

      {test && test !== 'running' && (
        <div className={`mt-6 rounded-lg border p-4 text-sm ${test.ok ? 'border-ok/40 bg-ok/5' : 'border-bad/40 bg-bad/5'}`}>
          <div className="flex items-center gap-2 font-medium">
            {test.ok ? <CheckCircle2 size={16} className="text-ok" /> : <XCircle size={16} className="text-bad" />}
            {test.ok ? `Connected to ${info.name}` : 'Connection failed'}
          </div>
          <p className="mt-1 text-paper-dim">{test.message}</p>
          {info.embeddings && s.embed_model && (
            <p className="mt-1 text-paper-dim">Embeddings: {test.embeddings ? 'working, semantic search on.' : `unavailable${test.embed_message ? ` (${test.embed_message})` : ''}. Keyword search will be used.`}</p>
          )}
        </div>
      )}
    </div>
  )
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-medium text-paper">{label}</span>
      {children}
      {hint && <span className="mt-1.5 block text-xs text-paper-mute">{hint}</span>}
    </label>
  )
}
