import { NextResponse } from 'next/server'
import { octokit } from '@/lib/github'

let cache: { data: any; timestamp: number } | null = null
const CACHE_DURATION = 10 * 60 * 1000

type Identity = {
  email?: string
  slackName?: string
  githubLogin?: string
  jiraName?: string
  aliases: string[]
}

export async function GET() {
  if (cache && Date.now() - cache.timestamp < CACHE_DURATION) {
    return NextResponse.json(cache.data)
  }

  const base = process.env.VERCEL_URL ? `https://${process.env.VERCEL_URL}` : 'http://localhost:3000'

  const [slackRaw, contributorsRaw, jiraRaw] = await Promise.all([
    fetch(`${base}/api/slack/messages`).then(r => r.json()).catch(() => ({ messages: [] })),
    fetch(`${base}/api/github/contributors`).then(r => r.json()).catch(() => ({})),
    fetch(`${base}/api/jira/issues`).then(r => r.json()).catch(() => []),
  ])

  const slackMessages = slackRaw.messages || []
  const slackUsers = new Map<string, { name: string; email?: string }>()
  for (const m of slackMessages) {
    if (m.userId) slackUsers.set(m.userId, { name: m.user, email: m.userEmail })
  }

  const ghLogins = Object.keys(contributorsRaw || {})

  const jiraNames = new Set<string>()
  for (const j of (Array.isArray(jiraRaw) ? jiraRaw : [])) {
    if (j.assignee && j.assignee !== 'Unassigned') jiraNames.add(j.assignee)
    if (j.reporter) jiraNames.add(j.reporter)
    for (const c of j.comments || []) if (c.author) jiraNames.add(c.author)
  }

  const ghEmails: Record<string, string> = {}
  await Promise.all(
    ghLogins.slice(0, 15).map(async login => {
      try {
        const u = await octokit.users.getByUsername({ username: login })
        if (u.data.email) ghEmails[login] = u.data.email
      } catch {}
    })
  )

  const identities = new Map<string, Identity>()

  function keyFor(seed: string): string {
    return seed.toLowerCase().trim()
  }

  function upsert(seedKey: string, patch: Partial<Identity>) {
    const k = keyFor(seedKey)
    const existing = identities.get(k) || { aliases: [] }
    const merged: Identity = {
      ...existing,
      ...patch,
      aliases: Array.from(new Set([...(existing.aliases || []), ...(patch.aliases || [])])),
    }
    identities.set(k, merged)
  }

  for (const [, u] of slackUsers) {
    const key = u.email || u.name
    upsert(key, { email: u.email, slackName: u.name, aliases: [u.name, ...(u.email ? [u.email] : [])] })
  }

  for (const login of ghLogins) {
    const email = ghEmails[login]
    if (email) {
      upsert(email, { email, githubLogin: login, aliases: [login, email] })
    } else {
      const matched = Array.from(identities.values()).find(i =>
        i.slackName && (
          i.slackName.toLowerCase().replace(/\s+/g, '') === login.toLowerCase() ||
          i.slackName.toLowerCase().includes(login.toLowerCase()) ||
          login.toLowerCase().includes(i.slackName.toLowerCase().split(' ')[0])
        )
      )
      if (matched) {
        const k = keyFor(matched.email || matched.slackName!)
        upsert(k, { githubLogin: login, aliases: [login] })
      } else {
        upsert(login, { githubLogin: login, aliases: [login] })
      }
    }
  }

  for (const jname of jiraNames) {
    const matched = Array.from(identities.values()).find(i =>
      i.slackName && i.slackName.toLowerCase().includes(jname.toLowerCase().split(' ')[0]) ||
      i.githubLogin && jname.toLowerCase().includes(i.githubLogin.toLowerCase())
    )
    if (matched) {
      const k = keyFor(matched.email || matched.slackName || matched.githubLogin!)
      upsert(k, { jiraName: jname, aliases: [jname] })
    } else {
      upsert(jname, { jiraName: jname, aliases: [jname] })
    }
  }

  const list = Array.from(identities.values())
    .filter(i => [i.slackName, i.githubLogin, i.jiraName].filter(Boolean).length >= 2)
  cache = { data: list, timestamp: Date.now() }
  return NextResponse.json(list)
}
