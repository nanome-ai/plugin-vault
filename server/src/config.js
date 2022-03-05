const config = {
  API_KEY: '',
  CONVERTER_URL: 'http://vault-converter:3000',
  ENABLE_AUTH: false,
  KEEP_FILES_DAYS: 0,
  UI_MESSAGE: '',
  USER_STORAGE: 0,
  USER_STORAGE_MSG: ''
}

const setUserStorageConfig = size => {
  const match = /^(?<num>\d+(\.\d+)?)(?<unit>[BbKkMmGg][Bb]?)?/.exec(size)
  const unit = (match.groups.unit[0] || '').toLowerCase()

  const n = { k: 1, m: 2, g: 3 }[unit] || 0
  const num = +match.groups.num

  config.USER_STORAGE = num * 1024 ** n
  config.USER_STORAGE_MSG = num + ['B', 'KB', 'MB', 'GB'][n]
}

// Check environment variables for configs
if (process.env.API_KEY) {
  config.API_KEY = process.env.API_KEY
}
if (process.env.CONVERTER_URL) {
  config.CONVERTER_URL = process.env.CONVERTER_URL
}
if (process.env.ENABLE_AUTH) {
  const enable = process.env.ENABLE_AUTH.toLowerCase()
  config.ENABLE_AUTH = enable === 'true'
}
if (process.env.KEEP_FILES_DAYS) {
  config.KEEP_FILES_DAYS = +process.env.KEEP_FILES_DAYS
}
if (process.env.UI_MESSAGE) {
  config.UI_MESSAGE = process.env.UI_MESSAGE
}
if (process.env.USER_STORAGE) {
  setUserStorageConfig(process.env.USER_STORAGE)
}

// Check cli args for configs
const args = process.argv.slice(2)
while (args.length) {
  const arg = args.shift()

  if (arg === '--api-key') {
    config.API_KEY = args.shift()
  } else if (['-c', '--converter-url'].includes(arg)) {
    config.CONVERTER_URL = args.shift()
  } else if (arg === '--enable-auth') {
    config.ENABLE_AUTH = true
  } else if (arg === '--keep-files-days') {
    config.KEEP_FILES_DAYS = +args.shift()
  } else if (arg === '--ui-message') {
    config.UI_MESSAGE = args.shift().replace(/_/g, ' ')
  } else if (arg === '--user-storage') {
    setUserStorageConfig(args.shift())
  }
}

module.exports = config
