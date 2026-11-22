import { Area, AreaChart, Bar as RBar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { fmt, Result } from '../lib/api'
import { Bar, chartTip, Empty, Panel, Section, Stat } from '../components/ui'

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

export default function ActivitySection({ r }: { r: Result }) {
  const g = r.git
  if (!g.available) {
    return <Section title="Activity"><Empty title="Commit history is unavailable">The repository was downloaded as an archive (git was unavailable or the clone failed), so commit statistics could not be read.</Empty></Section>
  }
  const contributors = g.contributors ?? []
  const totalC = contributors.reduce((s, c) => s + c.commits, 0) || 1
  const top = contributors[0]
  return (
    <Section title="Activity" lede={`Based on the most recent ${fmt.n(Math.min(400, g.commit_count ?? 0))} commits${g.shallow ? ' (recent history only)' : ''}.`}>
      <div className="panel grid grid-cols-2 gap-6 p-5 sm:grid-cols-4">
        <Stat value={g.commit_count ?? 0} label="commits" />
        <Stat value={contributors.length} label="contributors (sampled)" />
        <Stat value={fmt.ago(g.last_commit)} label="last commit" />
        <Stat value={top ? `${Math.round((top.commits / totalC) * 100)}%` : '—'} label="commits by top contributor" hint="A high share suggests a low bus factor" />
      </div>
      <div className="grid gap-6 xl:grid-cols-[1fr_340px]">
        <Panel title="Commits per week">
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={g.weekly}>
              <defs><linearGradient id="cw" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#4FC3C7" stopOpacity={0.4} /><stop offset="1" stopColor="#4FC3C7" stopOpacity={0} /></linearGradient></defs>
              <XAxis dataKey="week" tick={{ fill: '#8FA1BA', fontSize: 11 }} axisLine={false} tickLine={false} minTickGap={30} />
              <YAxis allowDecimals={false} tick={{ fill: '#8FA1BA', fontSize: 11 }} axisLine={false} tickLine={false} width={28} />
              <Tooltip {...chartTip} cursor={{ stroke: '#556E94' }} formatter={(v: any) => [v, 'commits']} labelFormatter={(l: any) => `Week ${l}`} />
              <Area type="monotone" dataKey="commits" stroke="#4FC3C7" fill="url(#cw)" strokeWidth={2} animationDuration={1100} animationEasing="ease-out" />
            </AreaChart>
          </ResponsiveContainer>
        </Panel>
        <Panel title="By weekday">
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={(g.weekday ?? []).map((v, i) => ({ d: DAYS[i], v }))}>
              <XAxis dataKey="d" tick={{ fill: '#8FA1BA', fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis hide />
              <Tooltip {...chartTip} formatter={(v: any) => [v, 'commits']} />
              <RBar dataKey="v" fill="#F0A04B" radius={[3, 3, 0, 0]} animationDuration={1100} animationEasing="ease-out" />
            </BarChart>
          </ResponsiveContainer>
        </Panel>
      </div>
      <div className="grid gap-6 xl:grid-cols-2">
        <Panel title="Contributors">
          <ul className="space-y-2.5">
            {contributors.slice(0, 12).map((c) => (
              <li key={c.name} className="grid grid-cols-[1fr_120px_60px] items-center gap-3 text-sm">
                <span className="truncate text-paper-dim" data-tip={`${c.name}: ${c.commits} commits, +${c.added} / −${c.deleted} lines`}>{c.name}</span>
                <Bar value={c.commits} max={top?.commits || 1} tone="contour" />
                <span className="text-right tabular-nums text-paper-mute">{c.commits}</span>
              </li>
            ))}
          </ul>
        </Panel>
        <Panel title="Recent commits">
          <ul className="space-y-2.5">
            {(g.recent_commits ?? []).slice(0, 12).map((c) => (
              <li key={c.sha} className="text-sm">
                <div className="truncate text-paper" data-tip={c.message.length > 70 ? c.message : undefined}>{c.message}</div>
                <div className="text-xs text-paper-mute">
                  <span className="font-mono">{c.sha}</span> · {c.author} · {fmt.ago(c.date)} · <span className="text-ok">+{c.added}</span> <span className="text-bad">−{c.deleted}</span>
                </div>
              </li>
            ))}
          </ul>
        </Panel>
      </div>
    </Section>
  )
}
