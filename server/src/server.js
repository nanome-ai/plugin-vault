require('module-alias/register')

const https = require('https')
const http = require('http')
const fs = require('fs')
const app = require('./app')
const config = require('./config')

const DEFAULT_PORT = 80
let HTTPS = false
let PORT = null

const args = process.argv.slice(2)
while (args.length) {
  const arg = args.shift()

  if (['-c', '--converter-url'].includes(arg)) {
    config.CONVERTER_URL = args.shift()
  } else if (arg === '--enable-auth') {
    config.ENABLE_AUTH = true
  } else if (arg === '--https') {
    HTTPS = true
  } else if (arg === '--keep-files-days') {
    config.KEEP_FILES_DAYS = args.shift()
  } else if (['-s', '--ssl-cert'].includes(arg)) {
    HTTPS = true
    args.shift()
  } else if (['-w', '--web-port'].includes(arg)) {
    PORT = args.shift()
  }
}

if (PORT === null) {
  PORT = HTTPS ? 443 : DEFAULT_PORT
}

let server
if (HTTPS) {
  const options = {
    key: fs.readFileSync('./certs/local.key'),
    cert: fs.readFileSync('./certs/local.cert')
  }
  server = https.createServer(options, app)
} else {
  server = http.createServer(app)
}

server.listen(PORT)

// TODO: cron services (auth and file cleanup)
