const crypto = require('crypto')

const ALGORITHM = 'aes-256-cbc'
const BLOCK_SIZE = 16
const HASH_ITERS = 8192

// brute force protection, key is hashed many times
const getKey = key => {
  for (let i = 0; i < HASH_ITERS; i++) {
    key = crypto.createHash('sha256').update(key).digest()
  }
  return key
}

exports.encrypt = (data, key) => {
  const iv = crypto.randomBytes(BLOCK_SIZE)
  const cipher = crypto.createCipheriv(ALGORITHM, getKey(key), iv)
  return Buffer.concat([iv, cipher.update(data), cipher.final()])
}

exports.decrypt = (data, key) => {
  const iv = data.slice(0, BLOCK_SIZE)
  data = data.slice(BLOCK_SIZE)
  const decipher = crypto.createDecipheriv(ALGORITHM, getKey(key), iv)
  return Buffer.concat([decipher.update(data), decipher.final()])
}
