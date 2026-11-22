import { useEffect, useState } from 'react'

/** True when the user asked the OS to reduce motion (Windows: Settings > Accessibility > Visual effects). */
export function useReducedMotion() {
  const q = typeof window !== 'undefined' ? window.matchMedia?.('(prefers-reduced-motion: reduce)') : null
  const [reduced, setReduced] = useState(!!q?.matches)
  useEffect(() => {
    if (!q) return
    const on = () => setReduced(q.matches)
    q.addEventListener?.('change', on)
    return () => q.removeEventListener?.('change', on)
  }, [q])
  return reduced
}

/** Animates a number from 0 to `value` once it is mounted. */
export function useCountUp(value: number, duration = 900) {
  const reduced = useReducedMotion()
  const [n, setN] = useState(reduced ? value : 0)
  useEffect(() => {
    if (reduced || !Number.isFinite(value)) { setN(value); return }
    let raf = 0
    const start = performance.now()
    const tick = (t: number) => {
      const p = Math.min(1, (t - start) / duration)
      const eased = 1 - Math.pow(1 - p, 3)
      setN(value * eased)
      if (p < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [value, duration, reduced])
  return n
}
