import { NextResponse } from 'next/server'

let cache: { data: any; timestamp: number } | null = null
const CACHE_DURATION = 2 * 60 * 1000

export async function GET(req: Request) {
  const debug = new URL(req.url).searchParams.get('debug') === '1'

  if (!debug && cache && Date.now() - cache.timestamp < CACHE_DURATION) {
    return NextResponse.json(cache.data)
  }

  const auth = Buffer.from(
    `${process.env.JIRA_EMAIL}:${process.env.JIRA_TOKEN}`
  ).toString('base64')

  const headers = {
    Authorization: `Basic ${auth}`,
    Accept: 'application/json',
    'Content-Type': 'application/json',
  }

  const res = await fetch(
    `https://${process.env.JIRA_DOMAIN}/rest/api/3/search/jql`,
    {
      method: 'POST',
      headers,
      body: JSON.stringify({
        jql: 'created >= -365d ORDER BY updated DESC',
        maxResults: 30,
        fields: ['summary', 'status', 'assignee', 'priority', 'updated', 'created', 'reporter', 'issuetype', 'labels', 'customfield_10020'],
      }),
    }
  )

  const data = await res.json()

  if (debug) {
    return NextResponse.json({
      status: res.status,
      ok: res.ok,
      domain: process.env.JIRA_DOMAIN,
      raw: data,
    })
  }

  if (!res.ok) {
    return NextResponse.json({ error: 'jira search failed', status: res.status, detail: data }, { status: 500 })
  }

  const issues = data.issues || []

  const enriched = await Promise.all(
    issues.slice(0, 20).map(async (issue: any) => {
      const [commentsRes, changelogRes] = await Promise.all([
        fetch(
          `https://${process.env.JIRA_DOMAIN}/rest/api/3/issue/${issue.key}/comment?maxResults=5&orderBy=-created`,
          { headers }
        ).catch(() => null),
        fetch(
          `https://${process.env.JIRA_DOMAIN}/rest/api/3/issue/${issue.key}?expand=changelog&fields=summary`,
          { headers }
        ).catch(() => null),
      ])
      const commentsData = commentsRes && commentsRes.ok ? await commentsRes.json() : { comments: [] }
      const comments = (commentsData.comments || []).map((c: any) => ({
        author: c.author?.displayName,
        created: c.created,
        text: extractText(c.body).slice(0, 300),
      }))

      const changelogData = changelogRes && changelogRes.ok ? await changelogRes.json() : null
      const statusTransitions = (changelogData?.changelog?.histories || [])
        .flatMap((h: any) =>
          (h.items || [])
            .filter((it: any) => it.field === 'status')
            .map((it: any) => ({
              when: h.created,
              who: h.author?.displayName,
              from: it.fromString,
              to: it.toString,
            }))
        )
        .slice(-5)

      const sprintField = issue.fields.customfield_10020
      const sprint = Array.isArray(sprintField) && sprintField.length
        ? { name: sprintField[0].name, state: sprintField[0].state }
        : null

      return {
        key: issue.key,
        summary: issue.fields.summary,
        status: issue.fields.status?.name,
        assignee: issue.fields.assignee?.displayName || 'Unassigned',
        reporter: issue.fields.reporter?.displayName,
        priority: issue.fields.priority?.name,
        type: issue.fields.issuetype?.name,
        labels: issue.fields.labels || [],
        updated: issue.fields.updated,
        created: issue.fields.created,
        sprint,
        comments,
        statusTransitions,
      }
    })
  )

  cache = { data: enriched, timestamp: Date.now() }
  return NextResponse.json(enriched)
}

function extractText(adf: any): string {
  if (!adf) return ''
  if (typeof adf === 'string') return adf
  if (adf.text) return adf.text
  if (Array.isArray(adf.content)) {
    return adf.content.map(extractText).join(' ')
  }
  return ''
}
