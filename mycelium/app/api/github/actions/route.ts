import { NextResponse } from 'next/server'
import { octokit } from '@/lib/github'

let cache: { data: any; timestamp: number } | null = null
const CACHE_DURATION = 5 * 60 * 1000

export async function GET() {
  if (cache && Date.now() - cache.timestamp < CACHE_DURATION) {
    return NextResponse.json(cache.data)
  }

  const repos = await octokit.repos.listForAuthenticatedUser({ per_page: 10, sort: 'pushed' })

  const runPromises = repos.data.map(async repo => {
    const runs = await octokit.actions.listWorkflowRunsForRepo({
      owner: repo.owner.login,
      repo: repo.name,
      per_page: 5,
    }).catch(() => ({ data: { workflow_runs: [] } }))

    return runs.data.workflow_runs.map((r: any) => ({
      repo: repo.name,
      name: r.name,
      status: r.status,
      conclusion: r.conclusion,
      branch: r.head_branch,
      author: r.actor?.login,
      created: r.created_at,
      url: r.html_url,
    }))
  })

  const results = await Promise.all(runPromises)
  const flat = results.flat()

  cache = { data: flat, timestamp: Date.now() }
  return NextResponse.json(flat)
}
