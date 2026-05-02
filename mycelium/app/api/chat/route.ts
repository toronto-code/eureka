import { NextRequest } from 'next/server'
import OpenAI from 'openai'
import { readStore, writeStore } from '@/lib/store'

const openai = new OpenAI({ apiKey: process.env.OPENAI_API_KEY })

const MAX_IMAGES = 4
const MAX_TRANSCRIPTS = 4
const MAX_AV_BYTES = 25 * 1024 * 1024

const STATIC_SYSTEM_PREFIX = `You are Mycelium — a company intelligence assistant for an engineering organization.

Your job: answer questions using the live data below, which spans GitHub (repos, commits, contributors, pull requests, issues, PR reviews, CI runs), Slack (messages, threads, reactions, pinned messages, attached files), and Jira (issues, comments, sprints, status changes).

Rules:
- Be concise. Use real names, repo names, ticket keys (like JIRA-123), PR numbers, and channel names — do not invent data.
- If the data shows nothing on a topic, say so plainly.
- When asked about cross-system links, use the LINKS section which auto-detects ticket-key mentions across systems.
- When asked about a person, use the IDENTITY GRAPH to combine their work across Slack/GitHub/Jira.
- If images are attached as message content, describe them when relevant.
- Format multi-item answers as short bullets.

---LIVE DATA---`

const VISION_KEYWORDS = /\b(image|picture|photo|screenshot|logo|diagram|chart|graph|drawing|design|mockup|figma|whiteboard|attached|attachment|visual|see|show|look|appears?|attached file)\b/i

type TranscriptStore = Record<string, { text: string; transcribedAt: number }>

async function downloadSlackImage(url: string): Promise<string | null> {
  try {
    const res = await fetch(url, { headers: { Authorization: `Bearer ${process.env.SLACK_TOKEN}` } })
    if (!res.ok) return null
    const buf = Buffer.from(await res.arrayBuffer())
    const mime = res.headers.get('content-type') || 'image/png'
    return `data:${mime};base64,${buf.toString('base64')}`
  } catch { return null }
}

async function transcribeSlackFile(fileId: string, url: string, name: string, mimetype: string, store: TranscriptStore): Promise<string | null> {
  if (store[fileId]?.text) return store[fileId].text
  try {
    const res = await fetch(url, { headers: { Authorization: `Bearer ${process.env.SLACK_TOKEN}` } })
    if (!res.ok) return null
    const buf = Buffer.from(await res.arrayBuffer())
    if (buf.length > MAX_AV_BYTES) return `[file too large: ${name}]`
    const file = new File([buf], name, { type: mimetype })
    const result = await openai.audio.transcriptions.create({ file, model: 'whisper-1' })
    store[fileId] = { text: result.text, transcribedAt: Date.now() }
    await writeStore('transcripts', store)
    return result.text
  } catch (e: any) {
    return `[transcription failed: ${e?.message || 'unknown'}]`
  }
}

function extractJiraKeys(text: string): string[] {
  const matches = (text || '').match(/\b[A-Z][A-Z0-9]+-\d+\b/g) || []
  return [...new Set(matches)]
}

function buildLinkGraph(commits: any[], slackMessages: any[], jiraIssues: any[], prs: any[]) {
  const jiraKeys = new Set(jiraIssues.map(j => j.key))
  const links: { type: string; from: string; to: string }[] = []

  for (const c of commits) {
    for (const key of extractJiraKeys(c.message || '')) {
      if (jiraKeys.has(key)) links.push({ type: 'commit→jira', from: `${c.repo}: ${(c.message || '').slice(0, 50)}`, to: key })
    }
  }
  for (const m of slackMessages) {
    for (const key of extractJiraKeys(m.text || '')) {
      if (jiraKeys.has(key)) links.push({ type: 'slack→jira', from: `#${m.channel} <${m.user}>`, to: key })
    }
  }
  for (const p of prs) {
    for (const key of extractJiraKeys(p.title || '') ) {
      if (jiraKeys.has(key)) links.push({ type: 'pr→jira', from: `${p.repo}#${p.number}`, to: key })
    }
  }
  return links
}

export async function POST(req: NextRequest) {
  const { messages } = await req.json()
  const userQuery = messages[messages.length - 1]?.content || ''
  const wantsImages = VISION_KEYWORDS.test(userQuery)

  const base = process.env.VERCEL_URL ? `https://${process.env.VERCEL_URL}` : 'http://localhost:3000'

  const [reposRaw, commitsRaw, contributorsRaw, prsRaw, issuesRaw, reviewsRaw, actionsRaw, slackRaw, jiraRaw, identityRaw] = await Promise.all([
    fetch(`${base}/api/github/repos`).then(r => r.json()).catch(() => []),
    fetch(`${base}/api/github/commits`).then(r => r.json()).catch(() => []),
    fetch(`${base}/api/github/contributors`).then(r => r.json()).catch(() => ({})),
    fetch(`${base}/api/github/prs`).then(r => r.json()).catch(() => []),
    fetch(`${base}/api/github/issues`).then(r => r.json()).catch(() => []),
    fetch(`${base}/api/github/reviews`).then(r => r.json()).catch(() => []),
    fetch(`${base}/api/github/actions`).then(r => r.json()).catch(() => []),
    fetch(`${base}/api/slack/messages`).then(r => r.json()).catch(() => ({ messages: [], pinned: [] })),
    fetch(`${base}/api/jira/issues`).then(r => r.json()).catch(() => []),
    fetch(`${base}/api/identity`).then(r => r.json()).catch(() => []),
  ])

  const slackMessages = slackRaw.messages || []
  const slackPinned = slackRaw.pinned || []

  const repos = (Array.isArray(reposRaw) ? reposRaw : []).slice(0, 8).map((r: any) =>
    `${r.owner?.login}/${r.name} (${r.language || '?'}) - ${(r.description || '').slice(0, 60)}`
  )

  const commitsArr = Array.isArray(commitsRaw) ? commitsRaw : []
  const commits = commitsArr.slice(0, 12).map((c: any) =>
    `${c.repo}: ${(c.message || '').slice(0, 70)} - ${c.author}`
  )

  const contributors = Object.entries(contributorsRaw || {}).slice(0, 8).map(
    ([name, info]: [string, any]) => `${name}: ${info.commits} commits across ${info.repos.length} repos`
  )

  const prsArr = Array.isArray(prsRaw) ? prsRaw : []
  const prs = prsArr.slice(0, 10).map((p: any) =>
    `${p.repo}#${p.number} [${p.merged ? 'merged' : p.state}] ${p.title} - ${p.author}`
  )

  const issuesArr = Array.isArray(issuesRaw) ? issuesRaw : []
  const issues = issuesArr.slice(0, 10).map((i: any) =>
    `${i.repo}#${i.number} [${i.state}] ${i.title} - ${i.author}${i.assignee ? ` (assigned: ${i.assignee})` : ''}`
  )

  const reviewsArr = Array.isArray(reviewsRaw) ? reviewsRaw : []
  const reviews = reviewsArr.slice(0, 8).flatMap((p: any) =>
    [
      ...p.reviews.slice(0, 2).map((r: any) => `${p.repo}#${p.number} review by ${r.user} [${r.state}]: ${r.body.slice(0, 80)}`),
      ...p.reviewComments.slice(0, 2).map((c: any) => `${p.repo}#${p.number} comment by ${c.user} on ${c.path}: ${c.body.slice(0, 80)}`),
    ]
  ).slice(0, 12)

  const actionsArr = Array.isArray(actionsRaw) ? actionsRaw : []
  const actions = actionsArr.slice(0, 8).map((a: any) =>
    `${a.repo} [${a.status}/${a.conclusion || '?'}] ${a.name} on ${a.branch} by ${a.author}`
  )

  const slack = slackMessages.slice(0, 18).map((m: any) => {
    const fileNote = m.files?.length ? ` [${m.files.length} file(s)]` : ''
    const reactionNote = m.reactions?.length ? ` [reactions: ${m.reactions.map((r: any) => `:${r.name}: ×${r.count}`).join(' ')}]` : ''
    const replyNote = m.in_reply_to ? ' (reply)' : ''
    return `#${m.channel} <${m.user}>${replyNote}: ${(m.text || '').slice(0, 100)}${fileNote}${reactionNote}`
  })

  const messagesByTs = new Map<string, any>()
  for (const m of slackMessages) messagesByTs.set(m.ts, m)
  const threadGroups: { channel: string; parent: any; replies: any[] }[] = []
  const seenParents = new Set<string>()
  for (const m of slackMessages) {
    if (m.in_reply_to && !seenParents.has(m.in_reply_to)) {
      const parent = messagesByTs.get(m.in_reply_to)
      const replies = slackMessages.filter((x: any) => x.in_reply_to === m.in_reply_to)
      if (parent) {
        threadGroups.push({ channel: m.channel, parent, replies })
        seenParents.add(m.in_reply_to)
      }
    }
  }

  const threads = threadGroups.slice(0, 6).map(g => {
    const head = `#${g.channel} THREAD parent <${g.parent.user}>: "${(g.parent.text || '').slice(0, 100)}"`
    const replyLines = g.replies.map((r: any) => `  ↳ <${r.user}> replied: "${(r.text || '').slice(0, 100)}"`)
    return [head, ...replyLines].join('\n')
  })

  const pinned = slackPinned.slice(0, 5).map((p: any) => `#${p.channel} pinned <${p.user}>: ${p.text.slice(0, 100)}`)

  const jiraArr = Array.isArray(jiraRaw) ? jiraRaw : []
  const jira = jiraArr.slice(0, 12).map((j: any) => {
    const sprintNote = j.sprint ? ` sprint=${j.sprint.name}` : ''
    const transitions = j.statusTransitions?.length ? ` history=[${j.statusTransitions.map((t: any) => `${t.from}→${t.to}`).join(',')}]` : ''
    return `${j.key} [${j.status}] ${j.priority || ''} ${j.type || ''}: ${j.summary} (${j.assignee})${sprintNote}${transitions}`
  })

  const jiraComments = jiraArr.flatMap((j: any) =>
    (j.comments || []).slice(0, 2).map((c: any) => `${j.key} <${c.author}>: ${c.text.slice(0, 120)}`)
  ).slice(0, 10)

  const links = buildLinkGraph(commitsArr, slackMessages, jiraArr, prsArr).slice(0, 15)

  const identity = (Array.isArray(identityRaw) ? identityRaw : []).slice(0, 12).map((i: any) =>
    `${[i.slackName && `slack:${i.slackName}`, i.githubLogin && `gh:${i.githubLogin}`, i.jiraName && `jira:${i.jiraName}`, i.email && `email:${i.email}`].filter(Boolean).join(' | ')}`
  )

  const transcriptStore = await readStore<TranscriptStore>('transcripts', {})
  const avFiles: { id: string; channel: string; user: string; name: string; mimetype: string; url: string }[] = []
  for (const m of slackMessages) {
    for (const f of m.files || []) {
      if (!f.url_private || !f.id) continue
      if ((f.mimetype?.startsWith('audio/') || f.mimetype?.startsWith('video/')) && avFiles.length < MAX_TRANSCRIPTS) {
        avFiles.push({ id: f.id, channel: m.channel, user: m.user, name: f.name, mimetype: f.mimetype, url: f.url_private })
      }
    }
  }
  const transcripts = await Promise.all(
    avFiles.map(async f => ({ ...f, text: await transcribeSlackFile(f.id, f.url, f.name, f.mimetype, transcriptStore) }))
  )
  const validTranscripts = transcripts.filter(t => t.text)

  let validImages: { channel: string; user: string; name: string; dataUrl: string | null }[] = []
  if (wantsImages) {
    const imageFiles: { channel: string; user: string; name: string; url: string }[] = []
    for (const m of slackMessages) {
      for (const f of m.files || []) {
        if (f.mimetype?.startsWith('image/') && f.url_private && imageFiles.length < MAX_IMAGES) {
          imageFiles.push({ channel: m.channel, user: m.user, name: f.name, url: f.url_private })
        }
      }
    }
    const downloaded = await Promise.all(
      imageFiles.map(async img => ({ ...img, dataUrl: await downloadSlackImage(img.url) }))
    )
    validImages = downloaded.filter(i => i.dataUrl)
  }

  const transcriptBlock = validTranscripts.length
    ? validTranscripts.map(t => `#${t.channel} <${t.user}> "${t.name}":\n"${t.text}"`).join('\n\n')
    : '(none)'

  const linksBlock = links.length
    ? links.map(l => `${l.type}: "${l.from}" → ${l.to}`).join('\n')
    : '(none detected)'

  const liveData = `
REPOS:
${repos.join('\n') || '(none)'}

PULL REQUESTS:
${prs.join('\n') || '(none)'}

PR REVIEWS & COMMENTS:
${reviews.join('\n') || '(none)'}

ISSUES:
${issues.join('\n') || '(none)'}

CI / WORKFLOW RUNS:
${actions.join('\n') || '(none)'}

COMMITS:
${commits.join('\n') || '(none)'}

CONTRIBUTORS:
${contributors.join('\n') || '(none)'}

SLACK MESSAGES:
${slack.join('\n') || '(no messages)'}

SLACK THREADS (parent → replies):
${threads.join('\n\n') || '(none)'}

SLACK PINNED:
${pinned.join('\n') || '(none)'}

SLACK AUDIO/VIDEO TRANSCRIPTS:
${transcriptBlock}

JIRA ISSUES:
${jira.join('\n') || '(none)'}

JIRA RECENT COMMENTS:
${jiraComments.join('\n') || '(none)'}

IDENTITY GRAPH (same person across systems):
${identity.join('\n') || '(none matched)'}

CROSS-SYSTEM LINKS (Jira keys mentioned in commits/Slack/PRs):
${linksBlock}`

  const useMini = !wantsImages && validImages.length === 0
  const model = useMini ? 'gpt-4o-mini' : 'gpt-4o'

  const chatMessages: any[] = [{ role: 'system', content: STATIC_SYSTEM_PREFIX + liveData }]

  if (validImages.length) {
    chatMessages.push({
      role: 'user',
      content: [
        { type: 'text', text: `Images recently shared in Slack:\n${validImages.map(i => `- #${i.channel} <${i.user}>: ${i.name}`).join('\n')}` },
        ...validImages.map(i => ({ type: 'image_url', image_url: { url: i.dataUrl, detail: 'low' } })),
      ],
    })
    chatMessages.push({ role: 'assistant', content: 'Got it, I have reviewed those images.' })
  }

  chatMessages.push(...messages)

  const stream = await openai.chat.completions.create({
    model,
    stream: true,
    max_tokens: 700,
    messages: chatMessages,
  })

  const encoder = new TextEncoder()
  const readable = new ReadableStream({
    async start(controller) {
      for await (const chunk of stream) {
        const text = chunk.choices[0]?.delta?.content || ''
        if (text) controller.enqueue(encoder.encode(text))
      }
      controller.close()
    },
  })

  return new Response(readable, {
    headers: {
      'Content-Type': 'text/plain; charset=utf-8',
      'X-Mycelium-Model': model,
    },
  })
}
