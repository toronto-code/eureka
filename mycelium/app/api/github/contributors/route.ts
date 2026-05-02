import { NextResponse } from 'next/server'
import { octokit } from '@/lib/github'

let cache: { data: any; timestamp: number } | null = null
const CACHE_DURATION = 10 * 60 * 1000

export async function GET() {
  if (cache && Date.now() - cache.timestamp < CACHE_DURATION) {
    return NextResponse.json(cache.data)
  }

  const repos = await octokit.repos.listForAuthenticatedUser({ per_page: 20 })
  const contribMap: Record<string, { repos: string[]; commits: number }> = {}

  for (const repo of repos.data) {
    const contributors = await octokit.repos.listContributors({
      owner: repo.owner.login,
      repo: repo.name,
    }).catch(() => ({ data: [] }))

    for (const c of contributors.data) {
      const login = c.login as string
      if (!contribMap[login]) contribMap[login] = { repos: [], commits: 0 }
      contribMap[login].repos.push(repo.name)
      contribMap[login].commits += c.contributions || 0
    }
  }

  cache = { data: contribMap, timestamp: Date.now() }
  return NextResponse.json(contribMap)
}
