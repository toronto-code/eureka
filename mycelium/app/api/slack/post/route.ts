import { NextRequest, NextResponse } from 'next/server'

export async function POST(req: NextRequest) {
  const { channel, text } = await req.json()
  if (!channel || !text) {
    return NextResponse.json({ error: 'channel and text required' }, { status: 400 })
  }

  const res = await fetch('https://slack.com/api/chat.postMessage', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${process.env.SLACK_TOKEN}`,
      'Content-Type': 'application/json; charset=utf-8',
    },
    body: JSON.stringify({ channel, text }),
  })
  const data = await res.json()
  if (!data.ok) {
    return NextResponse.json({ error: 'slack post failed', detail: data }, { status: 500 })
  }
  return NextResponse.json({ ok: true, ts: data.ts, channel: data.channel })
}
