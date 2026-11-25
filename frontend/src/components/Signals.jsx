import { Bar, BarChart, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import Badge from './Badge'

const ASSETS = ['', 'forex', 'crypto', 'index', 'commodity', 'stock']

function Controls({ t, s, set, meta }) {
  const num = k => e => set(k, e.target.value === '' ? '' : Number(e.target.value))
  return (
    <form className="controls" onSubmit={e => e.preventDefault()}>
      <label>{t('market')}
        <select value={s.asset} onChange={e => set('asset', e.target.value)}>
          {ASSETS.map(a => <option key={a} value={a}>{t(a || 'all')}</option>)}
        </select></label>
      <label>{t('timeframe')}
        <select value={s.timeframe} onChange={e => set('timeframe', e.target.value)}>
          <option value="1h">{t('h1')}</option><option value="1d">{t('d1')}</option>
        </select></label>
      <label>{t('capital')}
        <input type="number" inputMode="decimal" min="1" max="1000000000000" step="any" required value={s.capital} onChange={num('capital')} /></label>
      <label>{t('currency')}
        <select value={s.currency} onChange={e => set('currency', e.target.value)}>
          {meta.currencies.map(c => <option key={c}>{c}</option>)}
        </select></label>
      <label>{t('risk')}
        <input type="number" inputMode="decimal" min="0.1" max="5" step="0.1" required value={s.risk} onChange={num('risk')} /></label>
      <label>{t('topn')}
        <select value={s.top} onChange={num('top')}>{[3, 5, 10, 20].map(n => <option key={n}>{n}</option>)}</select></label>
    </form>
  )
}

function Position({ p, t, f }) {
  if (!p) return null
  return (
    <div className="pos">
      <span>{t('size')}: <b>{f.num(p.units)}</b> {t('units')}</span>
      <span>{t('atRisk')}: <b>{f.money(p.risk_amount, p.currency)}</b></span>
      <span>{t('leverage')}: <b>{f.num(p.leverage)}×</b></span>
      {p.capped && <em>{t('capped')}</em>}
    </div>
  )
}

function Card({ x, rank, t, f, onPick }) {
  return (
    <article className={`card ${x.direction.toLowerCase()}`}>
      <div className="row"><h3><span className="muted">{f.num(rank)}</span> {x.label}</h3><Badge dir={x.direction} t={t} /></div>
      <p className="big">{f.pct(x.p_win)} <small className="muted">{t('pwin')}</small></p>
      <p className="muted">{t('breakeven')} {f.pct(x.p_breakeven)} · {t('expected')} {f.r(x.expected_r)} R</p>
      <dl className="lv">
        <div><dt>{t('entry')}</dt><dd>{f.price(x.entry)}</dd></div>
        <div><dt>{t('stop')}</dt><dd>{f.price(x.stop)}</dd></div>
        <div><dt>{t('target')}</dt><dd>{f.price(x.target)}</dd></div>
      </dl>
      <Position p={x.position} t={t} f={f} />
      <button className="btn ghost" onClick={() => onPick(x.symbol)}>{t('details')}</button>
    </article>
  )
}

function Tip({ active, payload, t, f }) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return <div className="tip"><b>{d.label}</b><span>{t(d.lean)} · {t('pwin')} {f.pct(d.p_win)}</span><span>{t('breakeven')} {f.pct(d.p_breakeven)}</span></div>
}

export default function Signals({ t, f, s, set, meta, data, loading, onPick }) {
  const rows = data?.all_trades ?? []
  const bars = rows.map(r => ({ ...r, gap: (r.p_win - r.p_breakeven) * 100 })).sort((a, b) => b.gap - a.gap)
  const count = d => rows.filter(r => r.direction === d).length
  return (
    <>
      <Controls t={t} s={s} set={set} meta={meta} />
      {!data && loading && <p className="state" role="status">{t('loading')}</p>}
      {data && (
        <div className={loading ? 'dim' : ''} aria-busy={loading}>
          <div className="tiles">
            {['BUY', 'SELL', 'NEUTRAL'].map(d => <div key={d} className="tile"><b>{f.num(count(d))}</b><Badge dir={d} t={t} /></div>)}
            <div className="tile"><b>{f.num(rows.length)}</b><span className="muted">{t('everything')}</span></div>
            <div className="tile"><span className="muted">{t('asOf')}</span><span>{f.time(data.generated_at)}</span></div>
          </div>

          <section><h2>{t('top')}</h2>
            {data.top_trades.length === 0 ? <p className="state">{t('none')}</p>
              : <div className="cards">{data.top_trades.map((x, i) => <Card key={x.symbol} x={x} rank={i + 1} t={t} f={f} onPick={onPick} />)}</div>}
          </section>

          {bars.length > 0 && (
            <section><h2>{t('ranking')} <small className="muted">({t('points')})</small></h2>
              <div className="panel" dir="ltr">
                <div className="legend">{['BUY', 'SELL'].map(d => <span key={d}><i className={`sw ${d.toLowerCase()}`} />{t(d)}</span>)}</div>
                <ResponsiveContainer width="100%" height={bars.length * 24 + 40}>
                  <BarChart data={bars} layout="vertical" margin={{ left: 8, right: 24 }} barCategoryGap={4}>
                    <XAxis type="number" tick={{ fill: 'var(--muted)', fontSize: 12 }} axisLine={false} tickLine={false} tickFormatter={v => f.num(v)} />
                    <YAxis type="category" dataKey="label" width={92} interval={0} tick={{ fill: 'var(--ink2)', fontSize: 12 }} axisLine={false} tickLine={false} />
                    <Tooltip content={<Tip t={t} f={f} />} cursor={{ fill: 'var(--hover)' }} />
                    <ReferenceLine x={0} stroke="var(--muted)" />
                    <Bar dataKey="gap" radius={4} maxBarSize={14} isAnimationActive={false}>
                      {bars.map(b => <Cell key={b.symbol} fill={`var(--${b.lean.toLowerCase()})`} fillOpacity={b.direction === 'NEUTRAL' ? 0.45 : 1} />)}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </section>
          )}

          <section><h2>{t('everything')}</h2>
            <div className="scroll" tabIndex={0} role="region" aria-label={t('everything')}>
              <table>
                <thead><tr>{['instrument', 'signal', 'pwin', 'breakeven', 'expected', 'score', 'entry', 'stop', 'target'].map(k => <th key={k} scope="col">{t(k)}</th>)}</tr></thead>
                <tbody>{rows.map(r => (
                  <tr key={r.symbol}>
                    <th scope="row"><button className="link" onClick={() => onPick(r.symbol)}>{r.label}</button></th>
                    <td><Badge dir={r.direction} t={t} />{!r.fresh && <small className="muted"> {t('stale')}</small>}</td>
                    <td>{f.pct(r.p_win)}</td><td>{f.pct(r.p_breakeven)}</td><td>{f.r(r.expected_r)} R</td><td>{f.num(r.trade_score)}</td>
                    <td>{f.price(r.entry)}</td>
                    <td>{r.direction === 'NEUTRAL' ? '–' : f.price(r.stop)}</td><td>{r.direction === 'NEUTRAL' ? '–' : f.price(r.target)}</td>
                  </tr>))}</tbody>
              </table>
            </div>
            {data.missing.length > 0 && <p className="muted small">{t('missing')}: {data.missing.join(', ')}</p>}
          </section>
        </div>
      )}
    </>
  )
}
