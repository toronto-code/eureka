'use client'
import { useState } from 'react'

type Message = { role: 'user' | 'assistant'; content: string }

export default function Chat() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)

  async function send() {
    if (!input.trim()) return
    const userMsg: Message = { role: 'user', content: input }
    const newMessages = [...messages, userMsg]
    setMessages(newMessages)
    setInput('')
    setLoading(true)

    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ messages: newMessages }),
    })

    const reader = res.body!.getReader()
    const decoder = new TextDecoder()
    let assistantText = ''
    setMessages(m => [...m, { role: 'assistant', content: '' }])

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      assistantText += decoder.decode(value)
      setMessages(m => {
        const updated = [...m]
        updated[updated.length - 1] = { role: 'assistant', content: assistantText }
        return updated
      })
    }
    setLoading(false)
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{ flex: 1, overflowY: 'auto', padding: '16px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
        {messages.length === 0 && (
          <p style={{ color: '#888', fontSize: '14px', textAlign: 'center', marginTop: '40px' }}>
            Ask Mycelium anything about your company...
          </p>
        )}
        {messages.map((m, i) => (
          <div key={i} style={{
            alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start',
            background: m.role === 'user' ? '#1a1a1a' : '#f5f5f5',
            color: m.role === 'user' ? '#fff' : '#1a1a1a',
            padding: '10px 14px',
            borderRadius: '12px',
            maxWidth: '80%',
            fontSize: '14px',
            lineHeight: '1.5',
            whiteSpace: 'pre-wrap',
          }}>{m.content}</div>
        ))}
        {loading && <div style={{ fontSize: '12px', color: '#888' }}>Mycelium is thinking...</div>}
      </div>
      <div style={{ padding: '12px 16px', borderTop: '1px solid #eee', display: 'flex', gap: '8px' }}>
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && send()}
          placeholder="Who owns the payments service?"
          style={{ flex: 1, padding: '10px 14px', borderRadius: '8px', border: '1px solid #ddd', fontSize: '14px' }}
        />
        <button onClick={send} style={{ padding: '10px 18px', borderRadius: '8px', background: '#1a1a1a', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '14px' }}>
          Send
        </button>
      </div>
    </div>
  )
}
