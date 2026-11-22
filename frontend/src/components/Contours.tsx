import { useMemo } from 'react'

/** Procedural topographic contour lines — the home-page backdrop. Static (no motion). */
export default function Contours() {
  const paths = useMemo(() => {
    const out: string[] = []
    const centers = [[0.3, 0.42, 1], [0.72, 0.35, 0.8], [0.55, 0.78, 0.6]]
    for (const [cx, cy, s] of centers) {
      for (let r = 1; r <= 9; r++) {
        const pts: string[] = []
        const R = r * 46 * s
        for (let a = 0; a <= 64; a++) {
          const t = (a / 64) * Math.PI * 2
          const wob = 1 + 0.12 * Math.sin(3 * t + r * 0.7) + 0.07 * Math.cos(5 * t - r)
          const x = cx * 1200 + Math.cos(t) * R * 1.35 * wob
          const y = cy * 800 + Math.sin(t) * R * wob
          pts.push(`${a === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`)
        }
        out.push(pts.join(' ') + 'Z')
      }
    }
    return out
  }, [])
  return (
    <svg className="contours pointer-events-none absolute inset-0 h-full w-full" viewBox="0 0 1200 800" preserveAspectRatio="xMidYMid slice" aria-hidden>
      {paths.map((d, i) => (
        <path key={i} d={d} fill="none" stroke={i % 9 === 4 ? '#4FC3C7' : '#2B4060'} strokeWidth={i % 9 === 4 ? 1.1 : 0.8} opacity={i % 9 === 4 ? 0.55 : 0.7} />
      ))}
    </svg>
  )
}
