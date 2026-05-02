import { NextResponse } from 'next/server'

let cache: { data: any; timestamp: number } | null = null
let userCache: { data: Record<string, { name: string; email?: string }>; timestamp: number } | null = null
const CACHE_DURATION = 30 * 1000
const USER_CACHE_DURATION = 10 * 60 * 1000

async function slackFetch(method: string, params: Record<string, string> = {}) {
  const url = new URL(`https://slack.com/api/${method}`)
  Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v))
  const res = await fetch(url.toString(), {
    headers: { Authorization: `Bearer ${process.env.SLACK_TOKEN}` }
  })
  return res.json()
}

async function getUserMap(): Promise<Record<string, { name: string; email?: string }>> {
  if (userCache && Date.now() - userCache.timestamp < USER_CACHE_DURATION) {
    return userCache.data
  }
  const res = await slackFetch('users.list', { limit: '200' })
  const map: Record<string, { name: string; email?: string }> = {}
  for (const u of res.members || []) {
    map[u.id] = {
      name: u.real_name || u.profile?.real_name || u.name || u.id,
      email: u.profile?.email,
    }
  }
  userCache = { data: map, timestamp: Date.now() }
  return map
}

export async function GET(req: Request) {
  const debug = new URL(req.url).searchParams.get('debug') === '1'

  if (!debug && cache && Date.now() - cache.timestamp < CACHE_DURATION) {
    return NextResponse.json(cache.data)
  }

  const channelsRes = await slackFetch('conversations.list', {
    limit: '50',
    types: 'public_channel',
  })

  if (!channelsRes.ok) {
    return NextResponse.json({ error: 'slack conversations.list failed', detail: channelsRes }, { status: 500 })
  }

  const channels = channelsRes.channels || []
  const memberChannels = channels.filter((c: any) => c.is_member)

  const userMap = await getUserMap().catch(() => ({} as Record<string, { name: string; email?: string }>))

  const channelDataPromises = memberChannels.slice(0, 10).map(async (ch: any) => {
    const [history, pins] = await Promise.all([
      slackFetch('conversations.history', { channel: ch.id, limit: '20' }),
      slackFetch('pins.list', { channel: ch.id }).catch(() => ({ items: [] })),
    ])
    const msgs = history.messages || []

    const threadPromises = msgs
      .filter((m: any) => m.thread_ts && m.thread_ts === m.ts && m.reply_count > 0)
      .slice(0, 5)
      .map(async (parent: any) => {
        const replies = await slackFetch('conversations.replies', {
          channel: ch.id,
          ts: parent.ts,
          limit: '20',
        })
        return { parentTs: parent.ts, replies: replies.messages || [] }
      })

    const threadResults = await Promise.all(threadPromises)
    const threadMap: Record<string, any[]> = {}
    for (const tr of threadResults) {
      threadMap[tr.parentTs] = tr.replies.filter((r: any) => r.ts !== tr.parentTs)
    }

    const pinnedTexts = (pins.items || [])
      .filter((p: any) => p.message)
      .map((p: any) => ({
        text: (p.message.text || '').slice(0, 200),
        user: userMap[p.message.user]?.name || p.message.user,
        ts: p.message.ts,
      }))

    return {
      channel: ch.name,
      ok: history.ok,
      error: history.error,
      messages: msgs,
      threadMap,
      pinned: pinnedTexts,
    }
  })

  const results = await Promise.all(channelDataPromises)

  if (debug) {
    return NextResponse.json({
      totalChannels: channels.length,
      memberChannels: memberChannels.map((c: any) => c.name),
      userCount: Object.keys(userMap).length,
      usersWithEmail: Object.values(userMap).filter(u => u.email).length,
      results: results.map(r => ({
        channel: r.channel,
        ok: r.ok,
        error: r.error,
        messageCount: r.messages.length,
        threadCount: Object.keys(r.threadMap).length,
        filesCount: r.messages.reduce((n: number, m: any) => n + (m.files?.length || 0), 0),
        pinnedCount: r.pinned.length,
      })),
    })
  }

  function buildEntry(r: any, m: any, parentTs?: string) {
    const userInfo = userMap[m.user] || { name: m.user }
    return {
      channel: r.channel,
      text: m.text,
      user: userInfo.name,
      userId: m.user,
      userEmail: userInfo.email,
      ts: m.ts,
      thread_ts: m.thread_ts,
      in_reply_to: parentTs,
      reactions: (m.reactions || []).map((re: any) => ({
        name: re.name,
        count: re.count,
        users: (re.users || []).map((uid: string) => userMap[uid]?.name || uid),
      })),
      files: (m.files || []).map((f: any) => ({
        id: f.id,
        name: f.name,
        mimetype: f.mimetype,
        filetype: f.filetype,
        url_private: f.url_private,
      })),
    }
  }

  const flat = results.flatMap(r =>
    r.messages.flatMap((m: any) => {
      const main = buildEntry(r, m)
      const replies = (r.threadMap[m.ts] || []).map((rep: any) => buildEntry(r, rep, m.ts))
      return [main, ...replies]
    })
  )

  const allPinned = results.flatMap(r => r.pinned.map((p: any) => ({ ...p, channel: r.channel })))

  const payload = { messages: flat, pinned: allPinned }
  cache = { data: payload, timestamp: Date.now() }
  return NextResponse.json(payload)
}
