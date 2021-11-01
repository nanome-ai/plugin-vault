const fetch = require('node-fetch')

const config = require('@/config')
const { HTTPError } = require('./error')

const CACHE = {}

module.exports = async (req, res, next) => {
  const apiKey = req.headers['vault-api-key']
  if (apiKey && apiKey === config.API_KEY) return next()

  // path after /files/
  const path = req.path.slice(7)
  const userMatch = /^user-[0-9a-f]{8}/.exec(path)
  const orgMatch = /^org-\d+/.exec(path)

  const auth = req.headers.authorization
  if (!auth) {
    if (config.ENABLE_AUTH || userMatch || orgMatch) {
      return next(HTTPError.UNAUTHORIZED)
    } else return next()
  }

  const token = auth.split(' ').pop()
  let cached = CACHE[token]

  if (!cached) {
    const options = { headers: { Authorization: auth } }
    const res = await fetch('https://api.nanome.ai/user/session', options)
      .then(res => res.json())
      .catch(() => ({ success: false }))

    if (!res.success) return next(HTTPError.UNAUTHORIZED)
    cached = {
      user: res.results.user.unique,
      org: res.results.organization && `org-${res.results.organization.id}`
    }
    CACHE[token] = cached
  }

  const user = cached.user
  const org = cached.org
  cached.access = Date.now()

  if (userMatch && user !== userMatch[0]) {
    return next(HTTPError.UNAUTHORIZED)
  }

  if (orgMatch && org !== orgMatch[0]) {
    return next(HTTPError.UNAUTHORIZED)
  }

  next()
}

module.exports.CACHE = CACHE
