import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { RefreshCw, TriangleAlert, Info } from 'lucide-react'
import { get, load, save } from './api'
import { LANGS, detectLang, formatters, translator } from './i18n'
import Signals from './components/Signals'
import ModelReport from './components/ModelReport'
import TrackRecord from './components/TrackRecord'
import Detail from './components/Detail'
import Search from './components/Search'

const DEFAULTS = { timeframe: '1h', asset: '', capital: 10000, currency: 'USD', risk: 1, top: 5 }
const valid = s => s.capital > 0 && s.capital <= 1e12 && s.risk > 0 && s.risk <= 5

export default function App() {
  const [lang, setLang] = useState(() => load('lang', null) ?? detectLang())
  const [s, setS] = useState(() => ({ ...DEFAULTS, ...load('settings', {}) }))
  const [tab, setTab] = useState('signals')
  const [data, setData] = useState(null)
  const [meta, setMeta] = useState({ currencies: ['USD'] })
  const [report, setReport] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [tick, setTick] = useState(0)
  const [picked, setPicked] = useState(null)
  const first = useRef(true)

  const t = useMemo(() => translator(lang), [lang])
  const f = useMemo(() => formatters(lang), [lang])

  useEffect(() => {
    document.documentElement.lang = lang
    document.documentElement.dir = lang === 'ar' ? 'rtl' : 'ltr'
    save('lang', lang)
  }, [lang])

  useEffect(() => { get('/symbols').then(setMeta).catch(() => {}) }, [])

  useEffect(() => {
    const c = new AbortController()
    get('/model', { timeframe: s.timeframe }, c.signal).then(setReport).catch(() => setReport(null))
    return () => c.abort()
  }, [s.timeframe, tick])

  useEffect(() => {
    save('settings', s)
    if (!valid(s)) return
    const c = new AbortController()
    const id = setTimeout(async () => {              // debounce typing
      setLoading(true)
      try {
        setData(await get('/analyze', s, c.signal))
        setError(null)
      } catch (e) {
        if (e.name !== 'AbortError') setError(e.message)
      } finally {
        if (!c.signal.aborted) setLoading(false)
      }
    }, first.current ? 0 : 400)
    first.current = false
    return () => { clearTimeout(id); c.abort() }
  }, [s, tick])

  useEffect(() => {
    const id = setInterval(() => setTick(x => x + 1), 5 * 60 * 1000)
    return () => clearInterval(id)
  }, [])

  const set = useCallback((k, v) => setS(p => ({ ...p, [k]: v })), [])
  const ctx = { t, f, s, set, meta, lang }
  const shown = data?.timeframe === s.timeframe ? data : null

  return (
    <>
      <header className="top">
        <div className="brand"><strong>ITDSS</strong><span>{t('subtitle')}</span></div>
        <nav aria-label="ITDSS">
          {['signals', 'model', 'record'].map(k => (
            <button key={k} className="tab" aria-current={tab === k ? 'page' : undefined} onClick={() => setTab(k)}>{t(k)}</button>
          ))}
        </nav>
        <div className="actions">
          <Search {...ctx} onPick={setPicked} />
          <select aria-label={t('language')} value={lang} onChange={e => setLang(e.target.value)}>
            {Object.entries(LANGS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <button className="btn" onClick={() => setTick(x => x + 1)} disabled={loading} aria-label={t('refresh')}>
            <RefreshCw size={16} className={loading ? 'spin' : ''} aria-hidden /> <span className="wide">{t('refresh')}</span>
          </button>
        </div>
      </header>

      <main>
        {report && (
          <p className={`note ${report.edge_proven ? '' : 'warn'}`}>
            {report.edge_proven ? <Info size={18} aria-hidden /> : <TriangleAlert size={18} aria-hidden />}
            <span>{t(report.edge_proven ? 'edge' : 'noEdge')}</span>
          </p>
        )}
        {error && <p className="note bad" role="alert"><TriangleAlert size={18} aria-hidden /><span>{t('error')}: {error}</span></p>}
        {tab === 'signals' && <Signals {...ctx} data={shown} loading={loading} onPick={setPicked} />}
        {tab === 'model' && <ModelReport {...ctx} rep={report} />}
        {tab === 'record' && <TrackRecord {...ctx} tick={tick} />}
      </main>
      <footer>{t('disclaimer')}</footer>
      {picked && <Detail key={picked} {...ctx} symbol={picked} onClose={() => setPicked(null)} />}
    </>
  )
}
