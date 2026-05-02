'use client'
import { useEffect, useState } from 'react'

type Health = {
  github: 'ok' | 'error'
  slack: 'ok' | 'error'
  jira: 'ok' | 'error'
  lastChecked: string
}

export default function StatusPanel() {
  const [health, setHealth] = useState<Health | null>(null)

  const fetchHealth = () =>
    fetch('/api/health').then(r => r.json()).then(setHealth)

  useEffect(() => {
    fetchHealth()
    const interval = setInterval(fetchHealth, 30000)
    return () => clearInterval(interval)
  }, [])

  if (!health) return null

  const services = [
    { name: 'GitHub', status: health.github },
    { name: 'Slack',  status: health.slack  },
    { name: 'Jira',   status: health.jira   },
  ]

  return (
    <div style={{ padding: '12px 16px', borderTop: '1px solid #eee', display: 'flex', gap: '16px', alignItems: 'center' }}>
      {services.map(s => (
        <div key={s.name} style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <div style={{
            width: '8px', height: '8px', borderRadius: '50%',
            background: s.status === 'ok' ? '#22c55e' : '#ef4444'
          }}/>
          <span style={{ fontSize: '12px', color: '#666' }}>{s.name}</span>
        </div>
      ))}
      <span style={{ fontSize: '11px', color: '#aaa', marginLeft: 'auto' }}>
        Last synced {new Date(health.lastChecked).toLocaleTimeString()}
      </span>
    </div>
  )
}
