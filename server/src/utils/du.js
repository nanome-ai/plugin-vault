const { execSync } = require('child_process')

module.exports = path => {
  const result = execSync('du -sk', { cwd: path })
  const kbytes = /^(\d+)/.exec(result)
  return +kbytes[1] * 1024
}
