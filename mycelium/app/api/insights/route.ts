import { NextResponse } from 'next/server'
import OpenAI from 'openai'

const openai = new OpenAI({ apiKey: process.env.OPENAI_API_KEY })

let cache: { data: any; timestamp: number } | null = null
const CACHE_DURATION = 15 * 60 * 1000

export async function GET() {
  if (cache && Date.now() - cache.timestamp < CACHE_DURATION) {
    return NextResponse.json(cache.data)
  }

  const base = process.env.VERCEL_URL
    ? `https://${process.env.VERCEL_URL}`
    : 'http://localhost:3000'

  const [contributors, commits] = await Promise.all([
    fetch(`${base}/api/github/contributors`).then(r => r.json()).catch(() => {}),
    fetch(`${base}/api/github/commits`).then(r => r.json()).catch(() => []),
  ])

  const response = await openai.chat.completions.create({
    model: 'gpt-4o',
    response_format: { type: 'json_object' },
    messages: [{
      role: 'system',
      content: 'You are a company intelligence system. Return only valid JSON.',
    }, {
      role: 'user',
      content: `Analyze this engineering org data and return exactly 5 insights.
Return as JSON: { "insights": [ { "type": "alert" or "warning" or "info", "title": "short title", "description": "1-2 sentences" } ] }

Contributors: ${JSON.stringify(contributors)}
Recent commits: ${JSON.stringify(commits.slice(0, 20))}`,
    }]
  })

  const text = response.choices[0].message.content || '{}'
  const { insights } = JSON.parse(text)
  cache = { data: insights, timestamp: Date.now() }
  return NextResponse.json(insights)
}
