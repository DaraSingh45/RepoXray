import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

export default function Markdown({ children, onPath }: { children: string; onPath?: (path: string, line?: number) => void }) {
  return (
    <div className="md">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children }) => <a href={href} target="_blank" rel="noreferrer">{children}</a>,
          code: ({ className, children }) => {
            const text = String(children)
            // inline code that looks like `path/to/file.ext:12` becomes a link into the file viewer
            const m = !className && onPath ? text.match(/^([\w@./-]+\.[A-Za-z0-9]+)(?::(\d+))?(?:-\d+)?$/) : null
            if (m && m[1].includes('.')) {
              return (
                <code className="cursor-pointer hover:underline" onClick={() => onPath!(m[1], m[2] ? Number(m[2]) : undefined)}>
                  {text}
                </code>
              )
            }
            return <code className={className}>{children}</code>
          },
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  )
}
