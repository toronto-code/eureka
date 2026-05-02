import { NextResponse } from 'next/server'

async function check(url: string): Promise<'ok' | 'error'> {
  try {
    const res = await Promise.race([
      fetch(url),
      new Promise<never>((_, reject) =>
        setTimeout(() => reject(new Error('timeout')), 3000)
      )
    ]) as Response
    return res.ok ? 'ok' : 'error'
  } catch {
    return 'error'
  }
}

export async function GET() {
  const base = process.env.VERCEL_URL
    ? `https://${process.env.VERCEL_URL}`
    : 'http://localhost:3000'

  const [github, slack, jira] = await Promise.all([
    check(`${base}/api/github/repos`),
    check(`${base}/api/slack/messages`),
    check(`${base}/api/jira/issues`),
  ])

  return NextResponse.json({
    github, slack, jira,
    lastChecked: new Date().toISOString(),
  })
}
