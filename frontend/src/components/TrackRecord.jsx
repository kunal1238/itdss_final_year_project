import { useEffect, useState } from 'react'
import { get } from '../api'
import Badge from './Badge'

export default function TrackRecord({ t, f, s, set, tick }) {
  const [h, setH] = useState(null)
  useEffect(() => {
    const c = new AbortController()
    get('/history', { timeframe: s.timeframe }, c.signal).then(setH).catch(() => {})
    return () => c.abort()
  }, [s.timeframe, tick])
  return (
    <>
      <form className="controls"><label>{t('timeframe')}
        <select value={s.timeframe} onChange={e => set('timeframe', e.target.value)}><option value="1h">{t('h1')}</option><option value="1d">{t('d1')}</option></select></label></form>
      <p className="muted">{t('recordNote')}</p>
      {h && <div className="tiles">
        <div className="tile"><b>{f.num(h.closed)}</b><span className="muted">{t('closed')}</span></div>
        <div className="tile"><b>{f.num(h.open)}</b><span className="muted">{t('open')}</span></div>
        <div className="tile"><b>{f.pct(h.win_rate)}</b><span className="muted">{t('winrate')}</span></div>
        <div className="tile"><b>{f.r(h.avg_r)}</b><span className="muted">{t('avgR')}</span></div>
      </div>}
      {h && h.signals.length === 0 && <p className="state">{t('empty')}</p>}
      {h && h.signals.length > 0 && <div className="scroll"><table>
        <thead><tr>{['instrument', 'signal', 'asOf', 'pwin', 'entry', 'stop', 'target', 'status', 'avgR'].map(k => <th key={k} scope="col">{k === 'avgR' ? 'R' : t(k)}</th>)}</tr></thead>
        <tbody>{h.signals.map(x => <tr key={x.symbol + x.bar_time}><th scope="row">{x.symbol}</th><td><Badge dir={x.side > 0 ? 'BUY' : 'SELL'} t={t} /></td>
          <td>{f.time(x.bar_time)}</td><td>{f.pct(x.p_win)}</td><td>{f.price(x.entry)}</td><td>{f.price(x.stop)}</td><td>{f.price(x.target)}</td><td>{t(x.status)}</td><td>{f.r(x.r)}</td></tr>)}</tbody>
      </table></div>}
    </>
  )
}
