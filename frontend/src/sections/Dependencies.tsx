import { useMemo, useState } from 'react'
import { Result } from '../lib/api'
import { Empty, Section, Stat, Tag } from '../components/ui'

const REG: Record<string, (n: string) => string> = {
  npm: (n) => `https://www.npmjs.com/package/${n}`, pypi: (n) => `https://pypi.org/project/${n}/`, crates: (n) => `https://crates.io/crates/${n}`,
  go: (n) => `https://pkg.go.dev/${n}`, rubygems: (n) => `https://rubygems.org/gems/${n}`, packagist: (n) => `https://packagist.org/packages/${n}`,
  pub: (n) => `https://pub.dev/packages/${n}`, nuget: (n) => `https://www.nuget.org/packages/${n}`,
  maven: (n) => `https://central.sonatype.com/search?q=${encodeURIComponent(n.split(':')[1] ?? n)}`,
}

export default function Dependencies({ r }: { r: Result }) {
  const deps = r.dependencies.dependencies
  const [q, setQ] = useState('')
  const [filter, setFilter] = useState<'all' | 'outdated' | 'runtime' | 'dev'>('all')
  const counts = useMemo(() => ({
    major: deps.filter((d) => d.status === 'major').length, minor: deps.filter((d) => d.status === 'minor').length,
    current: deps.filter((d) => d.status === 'current' || d.status === 'patch').length, dev: deps.filter((d) => d.dev).length,
  }), [deps])
  const rows = deps
    .filter((d) => filter === 'all' || (filter === 'outdated' ? d.status === 'major' || d.status === 'minor' : filter === 'dev' ? d.dev : !d.dev))
    .filter((d) => d.name.toLowerCase().includes(q.toLowerCase()))
    .sort((a, b) => rank(a.status) - rank(b.status) || a.name.localeCompare(b.name))

  return (
    <Section title="Dependencies" lede="Every package declared in the repository’s manifests. Versions are compared with the latest releases on npm, PyPI, crates.io and the Go proxy.">
      {deps.length === 0 ? <Empty title="No dependency manifests found">No package.json, requirements.txt, pyproject.toml, go.mod, Cargo.toml, pom.xml or similar file was found.</Empty> : (
        <>
          <div className="panel grid grid-cols-2 gap-6 p-5 sm:grid-cols-5">
            <Stat value={deps.length} label="declared packages" />
            <Stat value={r.dependencies.manifests.length} label="manifests" />
            <Stat value={<span className={counts.major ? 'text-bad' : ''}>{counts.major}</span>} label="major versions behind" />
            <Stat value={<span className={counts.minor ? 'text-warn' : ''}>{counts.minor}</span>} label="minor versions behind" />
            <Stat value={counts.dev} label="development only" />
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <input className="input max-w-xs" placeholder="Search packages" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search packages" />
            {(['all', 'outdated', 'runtime', 'dev'] as const).map((f) => (
              <button key={f} onClick={() => setFilter(f)} aria-pressed={filter === f} className={`chip ${filter === f ? 'border-contour text-paper' : ''}`}>
                {{ all: 'All', outdated: 'Outdated', runtime: 'Runtime', dev: 'Development' }[f]}
              </button>
            ))}
          </div>
          <div className="panel overflow-x-auto">
            <table className="table-base">
              <thead><tr><th>Package</th><th>Declared</th><th>Latest</th><th>Status</th><th>Manifest</th></tr></thead>
              <tbody>
                {rows.slice(0, 400).map((d, i) => (
                  <tr key={i}>
                    <td>
                      <a href={REG[d.ecosystem]?.(d.name)} target="_blank" rel="noreferrer" className="font-mono text-[0.8rem] text-paper hover:text-contour">{d.name}</a>
                      {d.dev && <span className="ml-2 text-2xs text-paper-mute" data-tip="Only needed for development or testing">dev</span>}
                    </td>
                    <td className="font-mono text-xs text-paper-dim">{d.spec}</td>
                    <td className="font-mono text-xs text-paper-dim">{d.latest ?? '—'}</td>
                    <td data-tip={d.status === 'major' ? 'A new major version exists; upgrading may need code changes' : d.status === 'minor' ? 'Newer features are available' : d.status === 'patch' ? 'Bug-fix updates available' : d.status === 'unpinned' ? 'No exact version is pinned' : undefined}>{d.status ? <Tag tone={d.status}>{d.status === 'current' ? 'up to date' : d.status === 'unpinned' ? 'unpinned' : `${d.status} behind`}</Tag> : <span className="text-xs text-paper-mute">not checked</span>}</td>
                    <td className="text-xs text-paper-mute">{d.manifest}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </Section>
  )
}

function rank(s?: string) { return { major: 0, minor: 1, patch: 2, unpinned: 3, current: 4 }[s ?? ''] ?? 5 }
