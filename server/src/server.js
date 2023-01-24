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

https.createServer(options, app).listen(5001)
http.createServer(app).listen(5000)

cron.init()
