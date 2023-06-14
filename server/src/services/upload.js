const fs = require('fs-extra')
const ospath = require('path')
const fetch = require('node-fetch')
const FormData = require('form-data')

const config = require('@/config')
const Vault = require('@/services/vault-manager')
const { HTTPError } = require('@/utils/error')

const initUpload = (path, filename, key, size) => {
  Vault.checkStorageLimit(path, size)

  const id = Array.from({ length: 16 }, () =>
    Math.floor(Math.random() * 36).toString(36)
  ).join('')

  const dir = ospath.join(Vault.UPLOADS_DIR, id)
  fs.mkdirsSync(dir)
  fs.writeFileSync(ospath.join(dir, '.vinfo'), JSON.stringify({ path, key }))
  fs.writeFileSync(ospath.join(dir, filename), '')
  return id
}

const cancelUpload = id => {
  const dir = ospath.join(Vault.UPLOADS_DIR, id)
  fs.removeSync(dir)
}

const uploadChunk = async (headers, chunk) => {
  const id = headers['x-upload-id']
  if (!id) throw new HTTPError(400, 'Missing header: "X-Upload-Id"')

  const filename = headers['x-file-name']
  if (!filename) throw new HTTPError(400, 'Missing header: "X-File-Name"')

  const dir = ospath.join(Vault.UPLOADS_DIR, id)
  const filepath = ospath.join(dir, filename)
  if (!fs.existsSync(filepath)) {
    throw new HTTPError(400, 'Invalid upload')
  }

  const range = headers['content-range']
  if (!range) throw new HTTPError(400, 'Missing header: "Content-Range"')

  const match = range.match(/bytes (\d+)-(\d+)\/(\d+)/)
  if (!match) throw new HTTPError(400, 'Invalid header: "Content-Range"')

  const [, start, end, total] = match.map(Number)
  if (start >= total || start >= end || end > total) {
    throw new HTTPError(400, 'Invalid header: "Content-Range"')
  }

  const stats = fs.statSync(filepath)
  if (stats.size !== start) {
    throw new HTTPError(400, 'Invalid upload chunk')
  }

  fs.appendFileSync(filepath, fs.readFileSync(chunk.path))

  if (end === total) {
    const vinfo = fs.readFileSync(ospath.join(dir, '.vinfo'), 'utf8')
    const { path, key } = JSON.parse(vinfo)
    await finalizeUpload(filename, filepath, path, key)
    fs.removeSync(dir)
  }
}

const finalizeUpload = async (filename, filepath, path, key) => {
  let name = filename.replace(/[#?]/g, '_')
  const split = name.split('.')
  const ext = split.pop().toLowerCase()
  const base = split.join('.')
  name = `${base}.${ext}`

  let data = fs.readFileSync(filepath)
  if (Vault.EXTENSIONS.converted.includes(ext)) {
    const body = new FormData()
    body.append('files', data, name)

    const url = config.CONVERTER_URL + '/convert/office'
    data = await fetch(url, { method: 'POST', body }).then(res => res.buffer())
    name = base + '.pdf'
  }

  if (data) {
    Vault.addFile(path, name, data, key)
  }
}

module.exports = {
  initUpload,
  cancelUpload,
  uploadChunk,
  finalizeUpload
}
