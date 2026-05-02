import { Octokit } from '@octokit/rest'

export const octokit = new Octokit({
  auth: process.env.GITHUB_TOKEN,
})

export const USERNAME = process.env.GITHUB_USERNAME as string
