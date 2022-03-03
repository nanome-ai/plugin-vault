require('module-alias/register')

const https = require('https')
const http = require('http')
const fs = require('fs')
const app = require('./app')
const config = require('./config')
const cron = require('./services/cron')

// Check environment variables for configs
if(process.env.API_KEY && process.env.API_KEY != null){
  config.API_KEY = process.env.API_KEY
}
if(process.env.CONVERTER_URL && process.env.CONVERTER_URL != null) {
  config.CONVERTER_URL = process.env.CONVERTER_URL
}
if(process.env.ENABLE_AUTH && process.env.ENABLE_AUTH != null){
  config.ENABLE_AUTH = process.env.ENABLE_AUTH
}
if(process.env.KEEP_FILES_DAYS && process.env.KEEP_FILES_DAYS != null){
  config.KEEP_FILES_DAYS = process.env.KEEP_FILES_DAYS
}
if(process.env.UI_MESSAGE && process.env.UI_MESSAGE != null){
  config.UI_MESSAGE = process.env.UI_MESSAGE
}
if(process.env.USER_STORAGE && process.env.USER_STORAGE != null){
  config.USER_STORAGE = process.env.USER_STORAGE
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
    config.KEEP_FILES_DAYS = args.shift()
  } else if (arg === '--ui-message') {
    config.UI_MESSAGE = args.shift().replace(/_/g, ' ')
  } else if (arg === '--user-storage') {
    const size = args.shift()
    const match = /^(?<num>\d+(\.\d+)?)(?<unit>[BbKkMmGg][Bb]?)?/.exec(size)
    const unit = (match.groups.unit || '').toLowerCase()

    const n = { k: 1, m: 2, g: 3 }[unit] || 0
    const num = +match.groups.num

    config.USER_STORAGE = num * 1024 ** n
    config.USER_STORAGE_MSG = num + ['B', 'KB', 'MB', 'GB'][n]
  }
}

const options = {
  key: fs.readFileSync('./certs/local.key'),
  cert: fs.readFileSync('./certs/local.crt')
}

https.createServer(options, app).listen(443)
http.createServer(app).listen(80)

cron.init()
