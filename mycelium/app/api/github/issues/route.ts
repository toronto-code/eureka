import { NextResponse } from 'next/server'
import { octokit } from '@/lib/github'

let cache: { data: any; timestamp: number } | null = null
const CACHE_DURATION = 5 * 60 * 1000

export async function GET() {
  if (cache && Date.now() - cache.timestamp < CACHE_DURATION) {
    return NextResponse.json(cache.data)
  }

  const repos = await octokit.repos.listForAuthenticatedUser({ per_page: 10, sort: 'pushed' })

  const issuePromises = repos.data.map(async repo => {
    const issues = await octokit.issues.listForRepo({
      owner: repo.owner.login,
      repo: repo.name,
      state: 'all',
      per_page: 10,
      sort: 'updated',
      direction: 'desc',
    }).catch(() => ({ data: [] }))

    return issues.data
      .filter((i: any) => !i.pull_request)
      .map(i => ({
        repo: repo.name,
        number: i.number,
        title: i.title,
        state: i.state,
        author: i.user?.login,
        assignee: i.assignee?.login || null,
        labels: (i.labels || []).map((l: any) => typeof l === 'string' ? l : l.name),
        comments: i.comments,
        created: i.created_at,
        updated: i.updated_at,
        body: (i.body || '').slice(0, 200),
      }))
  })

  const results = await Promise.all(issuePromises)
  const flat = results.flat()

  cache = { data: flat, timestamp: Date.now() }
  return NextResponse.json(flat)
}
