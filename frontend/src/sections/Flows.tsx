import { useState } from 'react'
import { Result } from '../lib/api'
import Mermaid from '../components/Mermaid'
import { Empty, Section } from '../components/ui'

const DEFS = [
  { key: 'architecture', title: 'Layered architecture', desc: 'Modules grouped into layers (UI, API, logic, data), with the imports between them and the external services they use.' },
  { key: 'ai_flow', title: 'AI data-flow', desc: 'How data and control move through the main components, as described by the AI model.' },
  { key: 'execution', title: 'Execution flow', desc: 'What runs, starting from the main entry point and following its imports up to three levels deep.' },
  { key: 'request', title: 'Request lifecycle', desc: 'A typical request travelling through the detected frameworks, from the user to the data store and back.' },
  { key: 'lifecycle', title: 'Build & run', desc: 'The developer workflow inferred from manifests, scripts, Docker and CI configuration.' },
  { key: 'mindmap', title: 'Folder mind map', desc: 'The main directories at a glance.' },
] as const

export default function Flows({ r }: { r: Result }) {
  const available = DEFS.filter((d) => r.diagrams[d.key])
  const [cur, setCur] = useState<string>(available[0]?.key ?? 'architecture')
  const def = available.find((d) => d.key === cur) ?? available[0]

  return (
    <Section title="Flowcharts" lede="Diagrams generated from the code itself. Each one can be opened full screen, downloaded as SVG, or copied as Mermaid source for your own docs.">
      {available.length === 0 ? <Empty title="No diagrams for this repository">There is not enough code structure to draw flows from.</Empty> : (
        <>
          <div className="flex flex-wrap gap-1.5" role="tablist">
            {available.map((d) => (
              <button key={d.key} role="tab" aria-selected={cur === d.key} onClick={() => setCur(d.key)}
                className={`rounded-md px-3 py-1.5 text-sm ${cur === d.key ? 'bg-ink-600 text-paper' : 'text-paper-mute hover:text-paper'}`}>
                {d.title}
              </button>
            ))}
          </div>
          {def && (
            <div className="panel p-5">
              <p className="mb-4 text-sm text-paper-mute">{def.desc}</p>
              <Mermaid key={def.key} code={r.diagrams[def.key]!} title={def.title}
                fallback={def.key === 'ai_flow' ? r.diagrams.architecture : undefined} />
            </div>
          )}
        </>
      )}
    </Section>
  )
}
