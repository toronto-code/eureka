'use client'
import { useEffect, useState } from 'react'

type Insight = { type: 'alert' | 'warning' | 'info'; title: string; description: string }

const colors = {
  alert:   { border: '#ef4444', bg: '#fef2f2', text: '#991b1b' },
  warning: { border: '#f59e0b', bg: '#fffbeb', text: '#92400e' },
  info:    { border: '#3b82f6', bg: '#eff6ff', text: '#1e40af' },
}

export default function BulletinBoard() {
  const [insights, setInsights] = useState<Insight[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch('/api/insights')
      .then(r => r.json())
      .then(data => { setInsights(data); setLoading(false) })
  }, [])

  if (loading) return (
    <p style={{ fontSize: '13px', color: '#888', padding: '16px' }}>
      Mycelium is analyzing your company...
    </p>
  )

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', padding: '16px' }}>
      {insights.map((ins, i) => {
        const c = colors[ins.type]
        return (
          <div key={i} style={{
            borderLeft: `3px solid ${c.border}`,
            background: c.bg,
            borderRadius: '8px',
            padding: '12px 14px',
          }}>
            <p style={{ fontSize: '13px', fontWeight: 600, color: c.text, marginBottom: '4px' }}>{ins.title}</p>
            <p style={{ fontSize: '12px', color: '#555', lineHeight: '1.5' }}>{ins.description}</p>
          </div>
        )
      })}
    </div>
  )
}
