import { useEffect, useState } from 'react'
import { get } from '../api'

export default function Search({ t, onPick }) {
  const [q, setQ] = useState('')
  const [hits, setHits] = useState(null)

  useEffect(() => {
    if (q.trim().length < 2) return
    const c = new AbortController()
    const id = setTimeout(() => get('/search', { q: q.trim() }, c.signal).then(setHits).catch(e => e.name !== 'AbortError' && setHits([])), 350)
    return () => { clearTimeout(id); c.abort() }
  }, [q])

  const pick = sym => { onPick(sym); setQ(''); setHits(null) }
  const open = q.trim().length >= 2 && hits
  return (
    <div className="search" onKeyDown={e => e.key === 'Escape' && setQ('')}>
      <input type="search" value={q} onChange={e => setQ(e.target.value)} aria-label={t('search')} placeholder={t('searchHint')} />
      {open && (
        <ul>
          {hits.length === 0 && <li className="muted pad">{t('noResults')}</li>}
          {hits.map(h => (
            <li key={h.symbol}><button onClick={() => pick(h.symbol)}><b>{h.symbol}</b> {h.name} <small className="muted">{h.exchange}</small></button></li>
          ))}
        </ul>
      )}
    </div>
  )
}
