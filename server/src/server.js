require('module-alias/register')

const https = require('https')
const http = require('http')
const fs = require('fs')
const app = require('./app')
const cron = require('./services/cron')

const options = {
  key: fs.readFileSync('./certs/local.key'),
  cert: fs.readFileSync('./certs/local.crt')
}

const https_port = process.env.HTTPS_PORT || 443
const http_port = process.env.HTTP_PORT || 80
https.createServer(options, app).listen(https_port)
http.createServer(app).listen(http_port)

cron.init()
