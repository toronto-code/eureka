import { NextResponse } from 'next/server'
import { octokit } from '@/lib/github'

let cache: { data: any; timestamp: number } | null = null
const CACHE_DURATION = 5 * 60 * 1000

export async function GET() {
  if (cache && Date.now() - cache.timestamp < CACHE_DURATION) {
    return NextResponse.json(cache.data)
  }

  const repos = await octokit.repos.listForAuthenticatedUser({ per_page: 15, sort: 'pushed' })

  const prPromises = repos.data.map(async repo => {
    const prs = await octokit.pulls.list({
      owner: repo.owner.login,
      repo: repo.name,
      state: 'all',
      per_page: 10,
      sort: 'updated',
      direction: 'desc',
    }).catch(() => ({ data: [] }))
    return prs.data.map(p => ({
      repo: repo.name,
      number: p.number,
      title: p.title,
      state: p.state,
      merged: !!p.merged_at,
      author: p.user?.login,
      created: p.created_at,
      updated: p.updated_at,
      body: (p.body || '').slice(0, 200),
    }))
  })

  const results = await Promise.all(prPromises)
  const flat = results.flat()

  cache = { data: flat, timestamp: Date.now() }
  return NextResponse.json(flat)
}
