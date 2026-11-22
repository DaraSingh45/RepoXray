import { useEffect, useMemo, useRef } from 'react'
import hljs from 'highlight.js/lib/common'

const LANG: Record<string, string> = {
  Python: 'python', JavaScript: 'javascript', TypeScript: 'typescript', Go: 'go', Rust: 'rust', Java: 'java',
  Kotlin: 'kotlin', 'C#': 'csharp', 'C++': 'cpp', C: 'c', Ruby: 'ruby', PHP: 'php', Swift: 'swift', Shell: 'bash',
  HTML: 'xml', XML: 'xml', Vue: 'xml', Svelte: 'xml', CSS: 'css', SCSS: 'scss', Less: 'less', JSON: 'json', YAML: 'yaml',
  TOML: 'ini', Markdown: 'markdown', SQL: 'sql', Dockerfile: 'dockerfile', Makefile: 'makefile', Lua: 'lua', R: 'r',
  Perl: 'perl', 'Objective-C': 'objectivec', Scala: 'scala', Dart: 'dart', GraphQL: 'graphql',
}

function escape(s: string) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

/** Highlights code then splits into lines while keeping spans balanced. */
function highlightLines(code: string, language: string | null): string[] {
  let html: string
  const lang = language ? LANG[language] : undefined
  try {
    html = code.length > 300_000 ? escape(code) : lang && hljs.getLanguage(lang) ? hljs.highlight(code, { language: lang }).value : escape(code)
  } catch {
    html = escape(code)
  }
  const out: string[] = []
  let open: string[] = []
  for (const raw of html.split('\n')) {
    let line = open.join('') + raw
    const tags = raw.match(/<span[^>]*>|<\/span>/g) || []
    for (const t of tags) t.startsWith('</') ? open.pop() : open.push(t)
    line += '</span>'.repeat(open.length)
    out.push(line)
  }
  return out
}

export default function CodeView({ code, language, highlight }: { code: string; language: string | null; highlight?: number }) {
  const lines = useMemo(() => highlightLines(code, language), [code, language])
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (highlight && ref.current) {
      const el = ref.current.querySelector(`[data-line="${highlight}"]`)
      el?.scrollIntoView({ block: 'center' })
    }
  }, [highlight, code])
  return (
    <div ref={ref} className="code-view font-mono text-[0.78rem] leading-[1.6] overflow-auto h-full">
      <pre className="min-w-max py-2">
        {lines.map((l, i) => (
          <div key={i} data-line={i + 1} className={`row pr-6 ${highlight === i + 1 ? 'hl' : ''}`}>
            <span className="ln">{i + 1}</span>
            <span dangerouslySetInnerHTML={{ __html: l || ' ' }} />
          </div>
        ))}
      </pre>
    </div>
  )
}
