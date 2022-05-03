const cron = require('node-cron')
const fs = require('fs-extra')
const ospath = require('path')
const walk = require('@nodelib/fs.walk')
const config = require('@/config')
const auth = require('@/utils/auth')
const Vault = require('@/services/vault-manager')

const WALK_SETTINGS = new walk.Settings({
  entryFilter: e => !e.name.startsWith('.') && e.dirent.isFile(),
  stats: true
})

// remove tokens not used in 1 hour
const authCleanup = () => {
  const expiryTime = new Date()
  expiryTime.setHours(expiryTime.getHours() - 1)

  Object.entries(auth.CACHE).forEach(([token, data]) => {
    if (data.access < expiryTime) {
      delete auth.CACHE[token]
    }
  })
}

// remove files not accessed in KEEP_FILES_DAYS
const fileCleanup = () => {
  const expiryTime = new Date()
  expiryTime.setDate(expiryTime.getDate() - config.KEEP_FILES_DAYS)

  const files = walk.walkSync(Vault.FILES_DIR, WALK_SETTINGS)
  for (const file of files) {
    if (file.stats.atime < expiryTime) {
      fs.removeSync(file.path)
    }
  }
}

// remove abandoned uploads older than 10 min
const uploadCleanup = () => {
  const expiryTime = new Date()
  expiryTime.setMinutes(expiryTime.getMinutes() - 10)

  const items = fs.readdirSync(Vault.UPLOADS_DIR)
  for (const item of items) {
    const itemPath = ospath.join(Vault.UPLOADS_DIR, item)
    const stats = fs.statSync(itemPath)
    if (stats.mtime < expiryTime) {
      fs.removeSync(itemPath)
    }
  }
}

exports.init = () => {
  // run every 10 min
  cron.schedule('*/10 * * * *', authCleanup)
  cron.schedule('*/10 * * * *', uploadCleanup)

  if (config.KEEP_FILES_DAYS) {
    // run every hour
    cron.schedule('0 * * * *', fileCleanup)
  }
}
