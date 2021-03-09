require('module-alias/register')

const https = require('https')
const http = require('http')
const fs = require('fs')
const app = require('./app')
const config = require('./config')
const cron = require('./services/cron')

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
  }
}

const options = {
  key: fs.readFileSync('./certs/local.key'),
  cert: fs.readFileSync('./certs/local.cert')
}

https.createServer(options, app).listen(443)
http.createServer(app).listen(80)

cron.init()
