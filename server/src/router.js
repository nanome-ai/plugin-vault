const express = require('express')
const router = express.Router()

const config = require('@/config')
const Upload = require('@/services/upload')
const Vault = require('@/services/vault-manager')
const Zip = require('@/services/zip')
const asyncWrap = require('@/utils/async-wrap')
const auth = require('@/utils/auth')
const { HTTPError } = require('@/utils/error')

const STATIC_DIR = require('path').resolve('ui/dist')

router.get('/info', (req, res) => {
  res.success({
    extensions: Vault.EXTENSIONS,
    message: config.UI_MESSAGE,
    nanome2: config.NANOME2_URL
      ? { url: config.NANOME2_URL, toolId: config.NANOME2_TOOL_ID }
      : null
  })
})

// no auth header here: the id comes from an authorized 'zip' command and is
// only good once, so the browser can download it natively
router.get('/zip/:id/:name?', (req, res) => {
  const plan = Zip.take(req.params.id)
  if (!plan) throw new HTTPError(404, 'Download expired, please try again')
  Zip.send(plan, res)
})

router.get('/files(/*)?', auth, (req, res) => {
  const path = decodeURI(req.path).slice(7)

  const key = req.headers['vault-key']
  if (!Vault.isKeyValid(path, key)) {
    throw HTTPError.FORBIDDEN
  }

  const isFile = /\.[^/]+$/.test(path)
  if (!isFile) {
    const result = Vault.listPath(path)
    return res.success(result)
  }

  const data = Vault.getFile(path, key)
  return res.send(data)
})

router.post(
  '/files(/*)?',
  auth,
  asyncWrap(async (req, res) => {
    const path = decodeURI(req.path).slice(7)
    const { command, folder, name, key } = req.fields

    const needsKey = [
      'create',
      'delete',
      'rename',
      'upload',
      'upload-init',
      'zip'
    ].includes(command)
    if (needsKey && !Vault.isKeyValid(path, key)) throw HTTPError.FORBIDDEN

    if (!key && ['decrypt', 'encrypt', 'verify'].includes(command)) {
      throw new HTTPError(400, 'Missing arg: "key"')
    }

    switch (command) {
      case 'create':
        Vault.createPath(path)
        break

      case 'decrypt':
        Vault.decryptFolder(path, key)
        break

      case 'delete':
        Vault.deletePath(path)
        break

      case 'encrypt':
        Vault.encryptFolder(path, key)
        break

      case 'move':
        if (!folder) throw new HTTPError(400, 'Missing arg: "folder"')
        Vault.movePath(path, folder)
        break

      case 'rename':
        if (!name) throw new HTTPError(400, 'Missing arg: "name"')
        Vault.renamePath(path, name)
        break

      case 'upload':
        let { files } = req.files
        if (!Array.isArray(files)) files = [files]

        let failed = []
        const uploads = files.map(async file => {
          try {
            await Upload.finalizeUpload(file.name, file.path, path, key)
          } catch (e) {
            if (e instanceof HTTPError) throw e
            failed.push(file.name)
          }
        })

        await Promise.all(uploads)
        return res.success(failed.length ? { failed } : {})

      case 'upload-init':
        if (!name) throw new HTTPError(400, 'Missing arg: "name"')
        if (!req.fields.size) throw new HTTPError(400, 'Missing arg: "size"')
        const id = Upload.initUpload(path, name, key, req.fields.size)
        return res.success({ id })

      case 'upload-cancel':
        if (!req.fields.id) throw new HTTPError(400, 'Missing arg: "id"')
        Upload.cancelUpload(req.fields.id)
        break

      case 'upload-chunk':
        let { chunk } = req.files
        if (!chunk || Array.isArray(chunk)) {
          throw new HTTPError(400, 'Invalid upload chunk')
        }
        await Upload.uploadChunk(req.headers, chunk)
        break

      case 'verify':
        const success = Vault.isKeyValid(path, key)
        return res.success({ success })

      case 'zip':
        let items = []
        if (req.fields.items) {
          try {
            items = JSON.parse(req.fields.items)
          } catch (e) {
            throw new HTTPError(400, 'Invalid arg: "items"')
          }
          const valid = Array.isArray(items)
          if (!valid || !items.every(i => typeof i === 'string')) {
            throw new HTTPError(400, 'Invalid arg: "items"')
          }
        }

        const plan = Zip.plan(path, items, key, name)
        return res.success({
          id: Zip.create(plan),
          name: plan.name,
          files: plan.files,
          bytes: plan.bytes,
          skipped: plan.skipped
        })

      default:
        throw new HTTPError(400, 'Invalid command')
    }

    res.success()
  })
)

router.use(express.static(STATIC_DIR))
router.get('*', (req, res) => {
  res.sendFile(STATIC_DIR + '/index.html')
})

module.exports = router
