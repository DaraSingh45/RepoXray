import { useEffect, useRef, useState } from 'react'

/**
 * One global tooltip for the whole app. Any element with `data-tip="..."` gets a clear, high-contrast
 * tooltip on hover and on keyboard focus. It is positioned with fixed coordinates, so it is never
 * clipped by scrolling panels, and it flips below the element / stays inside the window near edges.
 */
export default function TooltipLayer() {
  const [tip, setTip] = useState<{ text: string; x: number; y: number; below: boolean } | null>(null)
  const timer = useRef<number>()
  const box = useRef<HTMLDivElement>(null)
  const [shift, setShift] = useState(0)

  useEffect(() => {
    const show = (el: HTMLElement) => {
      const text = el.getAttribute('data-tip')
      if (!text) return
      const r = el.getBoundingClientRect()
      const below = r.top < 70
      window.clearTimeout(timer.current)
      timer.current = window.setTimeout(() => setTip({ text, x: r.left + r.width / 2, y: below ? r.bottom + 8 : r.top - 8, below }), 120)
    }
    const hide = () => { window.clearTimeout(timer.current); setTip(null) }
    const over = (e: Event) => {
      const el = (e.target as HTMLElement)?.closest?.('[data-tip]') as HTMLElement | null
      el ? show(el) : hide()
    }
    document.addEventListener('mouseover', over)
    document.addEventListener('focusin', over)
    document.addEventListener('focusout', hide)
    document.addEventListener('scroll', hide, true)
    document.addEventListener('pointerdown', hide)
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && hide()
    document.addEventListener('keydown', esc)
    return () => {
      document.removeEventListener('mouseover', over); document.removeEventListener('focusin', over)
      document.removeEventListener('focusout', hide); document.removeEventListener('scroll', hide, true)
      document.removeEventListener('pointerdown', hide); document.removeEventListener('keydown', esc)
    }
  }, [])

  // keep the bubble inside the viewport horizontally
  useEffect(() => {
    if (!tip || !box.current) { setShift(0); return }
    const r = box.current.getBoundingClientRect()
    const pad = 8
    if (r.left < pad) setShift(pad - r.left)
    else if (r.right > window.innerWidth - pad) setShift(window.innerWidth - pad - r.right)
    else setShift(0)
  }, [tip])

  if (!tip) return null
  return (
    <div
      ref={box}
      role="tooltip"
      className="pointer-events-none fixed z-[100] max-w-xs whitespace-pre-line rounded-md border border-ink-400 bg-[#0A1320] px-2.5 py-1.5 text-[0.8rem] leading-snug text-paper shadow-lg shadow-black/40"
      style={{ left: tip.x + shift, top: tip.y, transform: `translate(-50%, ${tip.below ? '0' : '-100%'})` }}
    >
      {tip.text}
    </div>
  )
}
