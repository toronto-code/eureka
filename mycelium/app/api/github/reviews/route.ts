import { NextResponse } from 'next/server'
import { octokit } from '@/lib/github'

let cache: { data: any; timestamp: number } | null = null
const CACHE_DURATION = 5 * 60 * 1000

export async function GET() {
  if (cache && Date.now() - cache.timestamp < CACHE_DURATION) {
    return NextResponse.json(cache.data)
  }

  const repos = await octokit.repos.listForAuthenticatedUser({ per_page: 8, sort: 'pushed' })

  const repoData = await Promise.all(
    repos.data.map(async repo => {
      const prs = await octokit.pulls.list({
        owner: repo.owner.login,
        repo: repo.name,
        state: 'all',
        per_page: 5,
        sort: 'updated',
        direction: 'desc',
      }).catch(() => ({ data: [] }))

      const enriched = await Promise.all(
        prs.data.map(async pr => {
          const [reviewsRes, commentsRes] = await Promise.all([
            octokit.pulls.listReviews({
              owner: repo.owner.login,
              repo: repo.name,
              pull_number: pr.number,
            }).catch(() => ({ data: [] })),
            octokit.pulls.listReviewComments({
              owner: repo.owner.login,
              repo: repo.name,
              pull_number: pr.number,
              per_page: 5,
            }).catch(() => ({ data: [] })),
          ])

          return {
            repo: repo.name,
            number: pr.number,
            title: pr.title,
            author: pr.user?.login,
            reviews: reviewsRes.data.map(r => ({
              user: r.user?.login,
              state: r.state,
              body: (r.body || '').slice(0, 150),
              submitted: r.submitted_at,
            })),
            reviewComments: commentsRes.data.map(c => ({
              user: c.user?.login,
              path: c.path,
              body: (c.body || '').slice(0, 150),
              created: c.created_at,
            })),
          }
        })
      )

      return enriched.filter(p => p.reviews.length > 0 || p.reviewComments.length > 0)
    })
  )

  const flat = repoData.flat()
  cache = { data: flat, timestamp: Date.now() }
  return NextResponse.json(flat)
}
