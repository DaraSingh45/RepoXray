import { Bar as RBar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Result } from '../lib/api'
import { Bar, chartTip, Empty, Panel, Section } from '../components/ui'

const CAT_ORDER = ['Language', 'Frontend', 'Mobile', 'Desktop', 'Styling', 'State', 'Backend', 'API', 'Realtime', 'Database', 'ORM', 'Queue',
  'AI/ML', 'Data', 'Auth', 'Payments', 'Cloud', 'Build', 'Testing', 'Quality', 'DevOps', 'CI/CD', 'Hosting']

export default function Stack({ r }: { r: Result }) {
  const groups = CAT_ORDER.map((c) => [c, r.stack.filter((t) => t.category === c)] as const).filter(([, v]) => v.length)
  const langs = r.languages.filter((l) => l.lines > 0).slice(0, 12)

  return (
    <Section title="Tech stack" lede="Detected from manifests, configuration files and import statements. Hover a technology to see the evidence.">
      {r.stack.length === 0 ? <Empty title="No technologies detected">The repository has no recognised manifests or framework imports.</Empty> : (
        <div className="grid gap-x-10 gap-y-7 md:grid-cols-2 xl:grid-cols-3">
          {groups.map(([cat, items]) => (
            <div key={cat}>
              <h3 className="mb-2.5 text-sm text-paper-mute">{cat}</h3>
              <ul className="space-y-2">
                {items.map((t) => (
                  <li key={t.name} tabIndex={0} className="group border-l-2 border-ink-400 pl-3 hover:border-contour focus:border-contour" data-tip={`Found in:\n${t.evidence.join('\n')}`}>
                    <div className="font-medium text-paper">{t.name}</div>
                    <div className="truncate text-xs text-paper-mute">{t.description || t.evidence[0]}</div>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}

      <div className="grid gap-6 xl:grid-cols-2">
        <Panel title="Lines by language">
          {langs.length === 0 ? <p className="text-sm text-paper-mute">No text files.</p> : (
            <ResponsiveContainer width="100%" height={Math.max(160, langs.length * 30)}>
              <BarChart data={langs} layout="vertical" margin={{ left: 10, right: 20 }}>
                <XAxis type="number" tick={{ fill: '#8FA1BA', fontSize: 12 }} axisLine={false} tickLine={false} />
                <YAxis type="category" dataKey="name" width={110} tick={{ fill: '#A9B8CC', fontSize: 12 }} axisLine={false} tickLine={false} />
                <Tooltip {...chartTip}
                  formatter={(v: any, _n: any, p: any) => [`${Number(v).toLocaleString()} lines in ${p.payload.files} files`, 'Size']} />
                <RBar dataKey="lines" radius={[0, 4, 4, 0]} animationDuration={900} animationEasing="ease-out">{langs.map((l) => <Cell key={l.name} fill={l.color} />)}</RBar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </Panel>
        <Panel title="Most imported external packages">
          {r.external_imports.length === 0 ? <p className="text-sm text-paper-mute">No third-party imports detected.</p> : (
            <ul className="space-y-2">
              {r.external_imports.slice(0, 14).map((e) => {
                const max = r.external_imports[0].files
                return (
                  <li key={e.name} className="grid grid-cols-[140px_1fr_40px] items-center gap-3 text-sm">
                    <span className="truncate font-mono text-[0.8rem] text-paper-dim" data-tip={e.name.length > 18 ? e.name : undefined}>{e.name}</span>
                    <Bar value={e.files} max={max} tone="contour" />
                    <span className="text-right text-xs tabular-nums text-paper-mute">{e.files}</span>
                  </li>
                )
              })}
            </ul>
          )}
          <p className="mt-3 text-xs text-paper-mute">Number of files importing each package.</p>
        </Panel>
      </div>
    </Section>
  )
}
