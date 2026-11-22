// Typed client for the RepoXray API.

export type StepStatus = 'pending' | 'running' | 'done' | 'skipped' | 'failed'
export interface Step { key: string; label: string; status: StepStatus; detail: string; ms: number }

export interface AnalysisRow {
  id: string; url: string; owner: string; repo: string; ref: string | null
  status: 'queued' | 'running' | 'done' | 'failed'; progress: number; step: string; steps: Step[]
  error: string | null; created_at: number; updated_at: number
  description?: string | null; score?: number | null; language?: string | null
}
export interface Analysis extends AnalysisRow { result: Result | null }

export interface Lang { name: string; files: number; lines: number; bytes: number; color: string; percent: number; is_code: boolean }
export interface Tech { name: string; category: string; evidence: string[]; description: string }
export interface Dep { name: string; spec: string; ecosystem: string; manifest: string; dev: boolean; latest?: string; status?: 'major' | 'minor' | 'patch' | 'current' | 'unpinned' }
export interface TreeNode { name: string; path: string; type: 'dir' | 'file'; size: number; lines: number; files?: number; language?: string | null; complexity?: number; test?: boolean; children?: TreeNode[] }
export interface ModNode { id: string; label?: string; files: number; lines: number; complexity: number; language: string | null; layer: string; languages: Record<string, number> }
export interface Edge { source: string; target: string; weight: number }
export interface FileNode { id: string; language: string | null; lines: number; in: number; out: number; layer: string; test: boolean }
export interface FileRow { path: string; size: number; language: string | null; lines: number; complexity: number; test: boolean; code: boolean; binary: boolean; in: number; out: number }
export interface Symbol { name: string; kind: string; line: number; doc?: string; methods?: string[] }
export interface Route { method: string; path: string; file: string; line: number; framework: string }
export interface Improvement { title: string; detail: string; priority: string; category: string; effort?: string }
export interface Check { category: string; name: string; passed: boolean; score: number; weight: number; fix: string }

export interface Insights {
  source: 'heuristic' | 'llm'; model?: string; llm_error?: string
  summary: string; purpose: string; audience: string; use_cases: string[]
  how_it_works: { step: string; detail: string }[]
  key_components: { name: string; path: string; role: string }[]
  architecture: string
  learning_path: { path: string; why: string; exists?: boolean }[]
  improvements: Improvement[]
}

export interface Result {
  repo: string; url: string; subpath: string | null; fetch: { method: string; branch?: string; note?: string }
  meta: {
    full_name?: string; description?: string; homepage?: string; stars?: number; forks?: number; watchers?: number
    open_issues?: number; default_branch?: string; license?: string; topics?: string[]; created_at?: string
    pushed_at?: string; archived?: boolean; avatar?: string
  }
  project_type: string
  metrics: {
    files: number; total_files: number; truncated: boolean; source_files: number; test_files: number
    source_loc: number; test_loc: number; total_lines: number; size_bytes: number; functions: number
    avg_complexity: number; dirs: number; comment_ratio: number; test_ratio: number
  }
  languages: Lang[]; tree: TreeNode; files: FileRow[]
  dependencies: { dependencies: Dep[]; manifests: { path: string; ecosystem: string; count: number }[]; projects: any[] }
  external_imports: { name: string; files: number }[]
  stack: Tech[]
  modules: { nodes: ModNode[]; edges: Edge[] }
  file_graph: { nodes: FileNode[]; edges: Edge[]; total_edges: number }
  entry_points: { path: string; score: number; reasons: string[] }[]
  routes: Route[]
  symbols: Record<string, Symbol[]>
  git: {
    available: boolean; sha?: string; branch?: string; commit_count?: number; shallow?: boolean
    first_commit?: string; last_commit?: string
    recent_commits?: { sha: string; author: string; date: string; message: string; added: number; deleted: number; files: number }[]
    contributors?: { name: string; commits: number; added: number; deleted: number }[] | null
    weekly?: { week: string; commits: number }[]; weekday?: number[]
  }
  quality: {
    score: number; grade: string; categories: { name: string; score: number; passed: number; total: number }[]
    checks: Check[]; improvements: Improvement[]
    hotspots: { path: string; lines: number; complexity: number; functions: number; churn: number }[]
    stats: Record<string, number | null>
  }
  security: { severity: 'high' | 'medium' | 'low'; type: string; file: string; line: number; detail: string }[]
  todos: { path: string; line: number; kind: string; text: string }[]
  readme: { title?: string; intro?: string[]; features?: string[]; commands?: string[] }
  readme_path: string | null
  commands: Record<'install' | 'build' | 'test' | 'run' | 'docker' | 'from_readme', string[]>
  env_vars: { name: string; files: string[]; documented: boolean }[]
  diagrams: Partial<Record<'architecture' | 'execution' | 'request' | 'lifecycle' | 'mindmap' | 'ai_flow', string>>
  insights: Insights
  rag?: { chunks: number; dense: boolean; note: string }
  regenerating?: boolean
}

export type Provider = 'ollama' | 'groq' | 'gemini' | 'openai' | 'anthropic' | 'none'
export interface LLMSettings {
  provider: Provider; base_url: string; model: string; api_key: string
  embed_model: string; temperature: number; has_api_key: boolean; key_source: '' | 'settings' | 'env'
  profiles: Record<Provider, { base_url: string; model: string; embed_model: string }>
  keys: Partial<Record<Provider, '' | 'settings' | 'env'>>
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`/api${path}`, { headers: { 'content-type': 'application/json' }, ...init })
  if (!r.ok) {
    let msg = `${r.status} ${r.statusText}`
    try { const j = await r.json(); msg = j.detail || msg } catch { /* not json */ }
    throw new Error(msg)
  }
  return r.json()
}

export const api = {
  analyze: (url: string, force = false) => req<{ id: string; cached: boolean }>('/analyze', { method: 'POST', body: JSON.stringify({ url, force }) }),
  list: () => req<AnalysisRow[]>('/analyses'),
  get: (id: string) => req<Analysis>(`/analyses/${id}`),
  status: (id: string) => req<AnalysisRow>(`/analyses/${id}/status`),
  remove: (id: string) => req<{ ok: boolean }>(`/analyses/${id}`, { method: 'DELETE' }),
  file: (id: string, path: string) => req<{ path: string; content: string; symbols: Symbol[]; language: string | null }>(`/analyses/${id}/file?path=${encodeURIComponent(path)}`),
  explain: (id: string, path: string) => req<{ markdown: string; source: string }>(`/analyses/${id}/explain`, { method: 'POST', body: JSON.stringify({ path }) }),
  search: (id: string, q: string) => req<{ path: string; start: number; end: number; score: number; text: string }[]>(`/analyses/${id}/search?q=${encodeURIComponent(q)}`),
  regenerate: (id: string) => req<{ ok: boolean }>(`/analyses/${id}/insights/regenerate`, { method: 'POST' }),
  getLLM: () => req<LLMSettings>('/settings/llm'),
  putLLM: (s: Partial<LLMSettings> & { clear_api_key?: boolean }) => req<LLMSettings>('/settings/llm', { method: 'PUT', body: JSON.stringify(s) }),
  testLLM: () => req<{ ok: boolean; message: string; models: string[]; embeddings: boolean; embed_message?: string }>('/settings/llm/test', { method: 'POST' }),
  models: () => req<{ models: string[]; embed_models?: string[]; error?: string }>('/settings/llm/models'),
  health: () => req<{ ok: boolean; llm: LLMSettings }>('/health'),
}

export async function* chatStream(id: string, question: string, history: { role: string; content: string }[], signal?: AbortSignal) {
  const r = await fetch(`/api/analyses/${id}/chat`, {
    method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ question, history }), signal,
  })
  if (!r.ok || !r.body) {
    let msg = `${r.status}`
    try { msg = (await r.json()).detail } catch { /* ignore */ }
    throw new Error(msg)
  }
  const reader = r.body.getReader()
  const dec = new TextDecoder()
  let buf = ''
  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buf += dec.decode(value, { stream: true })
    let i
    while ((i = buf.indexOf('\n')) >= 0) {
      const line = buf.slice(0, i).trim()
      buf = buf.slice(i + 1)
      if (line) yield JSON.parse(line) as { type: 'sources' | 'token' | 'done'; data?: any }
    }
  }
}

export const fmt = {
  n: (v: number | undefined | null) => (v ?? 0).toLocaleString(),
  bytes: (b: number) => (b > 1e6 ? `${(b / 1e6).toFixed(1)} MB` : b > 1e3 ? `${(b / 1e3).toFixed(0)} KB` : `${b} B`),
  ago: (iso?: string | number | null) => {
    if (!iso) return '—'
    const t = typeof iso === 'number' ? iso * 1000 : Date.parse(iso)
    const d = (Date.now() - t) / 1000
    if (d < 60) return 'just now'
    if (d < 3600) return `${Math.floor(d / 60)} min ago`
    if (d < 86400) return `${Math.floor(d / 3600)} h ago`
    if (d < 86400 * 60) return `${Math.floor(d / 86400)} days ago`
    if (d < 86400 * 730) return `${Math.floor(d / 86400 / 30)} months ago`
    return `${Math.floor(d / 86400 / 365)} years ago`
  },
}
