import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Link, NavLink, Route, Routes } from 'react-router-dom'
import { Settings as SettingsIcon } from 'lucide-react'
import './index.css'
import Home from './pages/Home'
import Analysis from './pages/Analysis'
import Settings from './pages/Settings'
import TooltipLayer from './components/TooltipLayer'

function Logo() {
  return (
    <Link to="/" className="flex items-center gap-2.5 font-semibold tracking-tight text-paper">
      <svg width="26" height="26" viewBox="0 0 32 32" aria-hidden>
        <rect width="32" height="32" rx="7" fill="#15243A" />
        <g fill="none" stroke="#4FC3C7" strokeWidth="2"><ellipse cx="16" cy="16" rx="11" ry="8" /><ellipse cx="16" cy="16" rx="6.5" ry="4.5" /></g>
        <circle cx="16" cy="16" r="2" fill="#F0A04B" />
      </svg>
      RepoXray
    </Link>
  )
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-full flex flex-col">
      <header className="sticky top-0 z-40 border-b border-ink-500 bg-ink-800/90 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-[1500px] items-center justify-between px-5">
          <Logo />
          <nav className="flex items-center gap-1 text-sm">
            <NavLink to="/" end className={({ isActive }) => `btn-ghost ${isActive ? 'text-paper' : ''}`}>Analyses</NavLink>
            <NavLink to="/settings" className={({ isActive }) => `btn-ghost ${isActive ? 'text-paper' : ''}`}>
              <SettingsIcon size={15} /> Settings
            </NavLink>
          </nav>
        </div>
      </header>
      <main className="flex-1">{children}</main>
      <TooltipLayer />
    </div>
  )
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <Shell>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/a/:id" element={<Analysis />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="*" element={<div className="p-10 text-paper-mute">Page not found. <Link className="text-contour" to="/">Go home</Link></div>} />
        </Routes>
      </Shell>
    </BrowserRouter>
  </React.StrictMode>,
)
