import { NextResponse } from 'next/server'
import { octokit } from '@/lib/github'

let cache: { data: any; timestamp: number } | null = null
const CACHE_DURATION = 10 * 60 * 1000

export async function GET() {
  if (cache && Date.now() - cache.timestamp < CACHE_DURATION) {
    return NextResponse.json(cache.data)
  }

  const repos = await octokit.repos.listForAuthenticatedUser({ per_page: 10 })

  const commitPromises = repos.data.map(repo =>
    octokit.repos.listCommits({
      owner: repo.owner.login,
      repo: repo.name,
      per_page: 10,
    }).catch(() => ({ data: [] }))
  )

  const results = await Promise.all(commitPromises)
  const commits = results.flatMap(r => r.data).map(c => ({
    repo: c.url?.split('/')[5],
    message: c.commit.message.split('\n')[0],
    author: c.commit.author?.name,
    date: c.commit.author?.date,
  }))

  cache = { data: commits, timestamp: Date.now() }
  return NextResponse.json(commits)
}
