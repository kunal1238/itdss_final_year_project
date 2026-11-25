import { useEffect, useRef, useState } from 'react'
import { Bar, BarChart, Cell, Line, LineChart, PolarAngleAxis, PolarGrid, PolarRadiusAxis, Radar, RadarChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { X } from 'lucide-react'
import { get } from '../api'
import Badge from './Badge'

const clip = v => Math.max(0, Math.min(100, v))
const axis = { tick: { fill: 'var(--muted)', fontSize: 12 }, axisLine: false, tickLine: false }

function Tip({ active, payload, label, fmt }) {
  if (!active || !payload?.length) return null
  return <div className="tip">{label && <b>{label}</b>}{payload.map(p => <span key={p.dataKey}>{p.name}: {fmt(p.value)}</span>)}</div>
}

export default function Detail({ t, f, s, symbol, onClose }) {
  const ref = useRef(null)
  const [x, setX] = useState(null)
  const [px, setPx] = useState([])
  const [err, setErr] = useState(null)

  useEffect(() => { ref.current.showModal() }, [])
  useEffect(() => {
    const c = new AbortController()
    const p = encodeURIComponent(symbol)
    Promise.all([get(`/analyze/${p}`, s, c.signal), get(`/candles/${p}`, { timeframe: s.timeframe }, c.signal)])
      .then(([a, b]) => { setX(a); setPx(b) })
      .catch(e => e.name !== 'AbortError' && setErr(e.message))
    return () => c.abort()
  }, [symbol, s])

  const i = x?.indicators
  const radar = i && [
    { k: t('momentum'), v: clip(i.williams_r + 100) },
    { k: t('rsi'), v: clip(i.rsi) },
    { k: t('trend'), v: clip(50 + i.ema_spread * 8) },
    { k: t('volatility'), v: clip(i.atr_rel * 50) },
    { k: t('pwin'), v: clip(x.p_win * 100) },
  ]
  const traded = x && x.direction !== 'NEUTRAL'
  return (
    <dialog ref={ref} onClose={onClose} aria-label={symbol} onClick={e => e.target === ref.current && ref.current.close()}>
      <div className="dlg">
        <div className="row"><h2>{x?.label ?? symbol} {x && <Badge dir={x.direction} t={t} />}</h2>
          <button className="btn ghost" onClick={() => ref.current.close()} aria-label={t('close')}><X size={18} aria-hidden /></button></div>
        {err && <p className="note bad" role="alert">{t('error')}: {err}</p>}
        {!x && !err && <p className="state" role="status">{t('loading')}</p>}
        {x && (
          <>
            <p className="muted">{symbol} · {x.currency} · {t('asOf')} {f.time(x.bar_time)}</p>
            <p>{t('pwin')} <b>{f.pct(x.p_win)}</b> ({t(x.lean)}) · {t('breakeven')} <b>{f.pct(x.p_breakeven)}</b> · {t('expected')} <b>{f.r(x.expected_r)} R</b></p>
            {x.position && <p>{t('size')} <b>{f.num(x.position.units)}</b> {t('units')} · {t('atRisk')} <b>{f.money(x.position.risk_amount, x.position.currency)}</b> · {t('leverage')} <b>{f.num(x.position.leverage)}×</b></p>}
            <h3>{t('price')}</h3>
            <div className="legend"><span><i className="sw line1" />{t('price')}</span><span><i className="sw line2" />EMA 50</span><span><i className="sw line3" />EMA 200</span></div>
            <div dir="ltr"><ResponsiveContainer width="100%" height={240}>
              <LineChart data={px} margin={{ right: 56 }}>
                <XAxis dataKey="t" {...axis} minTickGap={60} tickFormatter={v => new Date(v).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })} />
                <YAxis {...axis} width={64} domain={['auto', 'auto']} tickFormatter={f.price} />
                <Tooltip content={<Tip fmt={f.price} />} labelFormatter={f.time} />
                {traded && [['entry', x.entry], ['stop', x.stop], ['target', x.target]].map(([k, v]) => (
                  <ReferenceLine key={k} y={v} stroke="var(--ink2)" strokeDasharray={k === 'entry' ? undefined : '5 4'} ifOverflow="extendDomain"
                    label={{ value: t(k), position: 'right', fill: 'var(--ink2)', fontSize: 11 }} />))}
                <Line dataKey="c" name={t('price')} stroke="var(--line1)" dot={false} strokeWidth={2} isAnimationActive={false} />
                <Line dataKey="f" name="EMA 50" stroke="var(--line2)" dot={false} strokeWidth={2} isAnimationActive={false} />
                <Line dataKey="s" name="EMA 200" stroke="var(--line3)" dot={false} strokeWidth={2} isAnimationActive={false} />
              </LineChart></ResponsiveContainer></div>
            <div className="two">
              <div><h3>{t('why')}</h3><p className="muted small">{t('whyNote')}</p>
                <div dir="ltr"><ResponsiveContainer width="100%" height={260}>
                  <BarChart data={x.drivers.map(d => ({ ...d, name: t(d.feature), pp: d.impact * 100 }))} layout="vertical" margin={{ right: 16 }}>
                    <XAxis type="number" {...axis} tickFormatter={v => f.r(v)} />
                    <YAxis type="category" dataKey="name" width={130} interval={0} {...axis} />
                    <Tooltip content={<Tip fmt={v => f.r(v)} />} cursor={{ fill: 'var(--hover)' }} />
                    <ReferenceLine x={0} stroke="var(--muted)" />
                    <Bar dataKey="pp" name={t('points')} radius={4} maxBarSize={14} isAnimationActive={false}>
                      {x.drivers.map(d => <Cell key={d.feature} fill={d.impact >= 0 ? 'var(--line1)' : 'var(--muted)'} />)}
                    </Bar>
                  </BarChart></ResponsiveContainer></div></div>
              <div><h3>{t('profile')}</h3>
                <div dir="ltr"><ResponsiveContainer width="100%" height={280}>
                  <RadarChart data={radar} outerRadius="65%">
                    <PolarGrid stroke="var(--line)" /><PolarAngleAxis dataKey="k" tick={{ fill: 'var(--ink2)', fontSize: 12 }} />
                    <PolarRadiusAxis domain={[0, 100]} tick={false} axisLine={false} />
                    <Radar dataKey="v" name="0–100" stroke="var(--line1)" strokeWidth={2} fill="var(--line1)" fillOpacity={0.2} isAnimationActive={false} />
                    <Tooltip content={<Tip fmt={v => f.num(v)} />} />
                  </RadarChart></ResponsiveContainer></div></div>
            </div>
          </>
        )}
      </div>
    </dialog>
  )
}
