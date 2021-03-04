const fetch = require('node-fetch')

const config = require('@/config')
const Vault = require('@/services/vault-manager')
const { HTTPError } = require('./error')

const AUTH_CACHE = {}

module.exports = async (req, res, next) => {
  if (!config.ENABLE_AUTH) return next()

  const auth = req.headers.authorization
  if (!auth) return next(HTTPError.UNAUTHORIZED)

  const token = auth.split(' ').pop()
  let cached = AUTH_CACHE[token]

  if (!cached) {
    const options = { headers: { Authorization: auth } }
    const res = await fetch('https://api.nanome.ai/user/session', options)
      .then(res => res.json())
      .catch(() => ({ success: false }))

    if (!res.success) return next(HTTPError.UNAUTHORIZED)
    cached = { user: res.results.user.unique }
    AUTH_CACHE[token] = cached
  }

  let user = null
  if (cached) {
    user = cached.user
    cached.access = Date.now()
  }

  const path = req.path.slice(1)
  const regex = /^user-[0-9a-f]{8}/
  const match = regex.exec(path)
  if (!user || (match && user !== match[0])) {
    return next(HTTPError.UNAUTHORIZED)
  }

  next()
}
