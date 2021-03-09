const fetch = require('node-fetch')

const config = require('@/config')
const { HTTPError } = require('./error')

const CACHE = {}

module.exports = async (req, res, next) => {
  if (!config.ENABLE_AUTH) return next()

  const apiKey = req.headers['vault-api-key']
  if (apiKey && apiKey === config.API_KEY) return next()

  const auth = req.headers.authorization
  if (!auth) return next(HTTPError.UNAUTHORIZED)

  const token = auth.split(' ').pop()
  let cached = CACHE[token]

  if (!cached) {
    const options = { headers: { Authorization: auth } }
    const res = await fetch('https://api.nanome.ai/user/session', options)
      .then(res => res.json())
      .catch(() => ({ success: false }))

    if (!res.success) return next(HTTPError.UNAUTHORIZED)
    cached = { user: res.results.user.unique }
    CACHE[token] = cached
  }

  const user = cached.user
  cached.access = Date.now()

  const path = req.path.slice(1)
  const regex = /^user-[0-9a-f]{8}/
  const match = regex.exec(path)
  if (match && user !== match[0]) {
    return next(HTTPError.UNAUTHORIZED)
  }

  next()
}

module.exports.CACHE = CACHE
