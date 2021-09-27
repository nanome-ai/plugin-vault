const express = require('express')
const app = express()
const formidable = require('express-formidable')

// response helpers
express.response.success = function (data) {
  return this.json({
    success: true,
    ...data
  })
}

express.response.error = function (error, statusCode) {
  const status = statusCode || error.status || 500

  return this.status(status).json({
    success: false,
    error: {
      status,
      message: error.message
    }
  })
}

app.use(require('morgan')('dev')) // logging
app.use(require('helmet')({ contentSecurityPolicy: false }))
app.use(require('compression')())
app.use(formidable({ multiples: true, maxFileSize: 1024 ** 3 }))
app.use(require('./router'))

// error handling
app.use((error, req, res, next) => {
  res.error(error)
})

module.exports = app
