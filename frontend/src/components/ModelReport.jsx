import { useState } from 'react'
import { Bar, BarChart, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { retrain } from '../api'

const NAMES = { majority: 'Majority class (no skill)', rule_only: 'Rule only (%R + EMA)', logistic: 'Logistic regression', tree: 'Decision tree', gradient_boosting: 'Gradient boosting', random_forest: 'Random Forest (ITDSS)', buy_and_hold: 'Buy and hold' }
const axis = { tick: { fill: 'var(--muted)', fontSize: 12 }, axisLine: false, tickLine: false }

function Tip({ active, payload, fmt }) {
  if (!active || !payload?.length) return null
  return <div className="tip">{payload.map(p => <span key={p.dataKey}>{p.name}: {fmt(p.value)}</span>)}</div>
}

function Retrain({ t, s }) {
  const [token, setToken] = useState('')
  const [msg, setMsg] = useState('')
  const go = async e => {
    e.preventDefault()
    try { await retrain(s.timeframe, token); setMsg(t('started')) } catch (x) { setMsg(x.message) }
  }
  return (
    <form className="controls" onSubmit={go}>
      <label>{t('token')}<input type="password" autoComplete="off" required value={token} onChange={e => setToken(e.target.value)} /></label>
      <button className="btn">{t('retrain')} {s.timeframe}</button><span role="status">{msg}</span>
    </form>
  )
}

export default function ModelReport({ t, f, s, set, rep }) {
  const pick = (
    <form className="controls"><label>{t('timeframe')}
      <select value={s.timeframe} onChange={e => set('timeframe', e.target.value)}><option value="1h">{t('h1')}</option><option value="1d">{t('d1')}</option></select></label></form>
  )
  if (!rep) return <>{pick}<p className="state">{t('loading')}</p></>
  const rf = rep.results.random_forest
  const total = rf.confusion.flat().reduce((a, b) => a + b, 0)
  const cal = rf.calibration.map(([p, a]) => ({ p, a, i: p }))
  const imp = Object.entries(rep.importance).map(([k, v]) => ({ k: t(k), v })).sort((a, b) => b.v - a.v)
  return (
    <>
      {pick}
      <p className="muted">{t('oos')}: {rep.oos.join(' → ')} · {t('trained')}: {f.time(rep.trained_at)} · n = {f.num(rep.n_oos)}</p>
      <section><h2>{t('compare')}</h2>
        <div className="scroll" tabIndex={0} role="region" aria-label={t('compare')}><table>
          <thead><tr>{['method', 'accuracy', 'balanced', 'trades', 'winrate', 'avgR', 'ci', 'pf', 'sharpe', 'drawdown'].map(k => <th key={k} scope="col">{t(k)}</th>)}</tr></thead>
          <tbody>{Object.keys(NAMES).map(k => { const r = rep.results[k]; return (
            <tr key={k} className={k === 'random_forest' ? 'hl' : ''}><th scope="row">{NAMES[k]}</th>
              <td>{f.pct(r.accuracy)}</td><td>{f.pct(r.balanced_accuracy)}</td><td>{f.num(r.trades)}</td><td>{f.pct(r.win_rate)}</td>
              <td>{f.r3(r.avg_r)}</td><td>{r.ci ? `${f.r3(r.ci[0])} … ${f.r3(r.ci[1])}` : '–'}</td><td>{f.num(r.profit_factor)}</td><td>{f.num(r.sharpe)}</td><td>{f.pct(r.max_drawdown)}</td></tr>) })}</tbody>
        </table></div></section>
      <div className="two">
        <section className="panel"><h2>{t('calibration')}</h2>
          <div className="legend"><span><i className="sw line1" />{t('actual')}</span><span><i className="sw dash" />{t('ideal')}</span></div>
          <div dir="ltr"><ResponsiveContainer width="100%" height={260}><LineChart data={cal} margin={{ right: 16 }}>
            <XAxis type="number" dataKey="p" domain={['auto', 'auto']} {...axis} tickFormatter={f.pct} /><YAxis {...axis} width={52} domain={['auto', 'auto']} tickFormatter={f.pct} />
            <Tooltip content={<Tip fmt={f.pct} />} />
            <Line dataKey="i" name={t('predicted')} stroke="var(--muted)" strokeDasharray="5 4" dot={false} isAnimationActive={false} />
            <Line dataKey="a" name={t('actual')} stroke="var(--line1)" strokeWidth={2} dot={{ r: 4 }} isAnimationActive={false} />
          </LineChart></ResponsiveContainer></div></section>
        <section className="panel"><h2>{t('importance')}</h2>
          <div dir="ltr"><ResponsiveContainer width="100%" height={280}><BarChart data={imp} layout="vertical" margin={{ right: 16 }}>
            <XAxis type="number" {...axis} /><YAxis type="category" dataKey="k" width={140} interval={0} {...axis} />
            <Tooltip content={<Tip fmt={v => v} />} cursor={{ fill: 'var(--hover)' }} /><ReferenceLine x={0} stroke="var(--muted)" />
            <Bar dataKey="v" name="Δ log-loss" fill="var(--line1)" radius={4} maxBarSize={14} isAnimationActive={false} />
          </BarChart></ResponsiveContainer></div></section>
      </div>
      <section><h2>{t('confusion')}</h2><div className="scroll"><table>
        <thead><tr><th scope="col">{t('actual')} ↓ / {t('predicted')} →</th>{['SELL', 'NEUTRAL', 'BUY'].map(k => <th key={k} scope="col">{t(k)}</th>)}</tr></thead>
        <tbody>{rf.confusion.map((row, i) => <tr key={i}><th scope="row">{t(['SELL', 'NEUTRAL', 'BUY'][i])}</th>{row.map((v, j) => <td key={j}>{f.num(v)} <small className="muted">{f.pct(v / total)}</small></td>)}</tr>)}</tbody>
      </table></div></section>
      <Retrain t={t} s={s} />
    </>
  )
}
