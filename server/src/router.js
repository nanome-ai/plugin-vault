const express = require('express')
const router = express.Router()

const fs = require('fs')
const ospath = require('path')
const fetch = require('node-fetch')
const FormData = require('form-data')
const config = require('./config')

const Vault = require('@/services/vault-manager')
const asyncWrap = require('@/utils/async-wrap')
const auth = require('@/utils/auth')
const { HTTPError } = require('@/utils/error')

const STATIC_DIR = ospath.resolve('ui/dist')

router.get('/info', (req, res) => {
  res.success({ extensions: Vault.EXTENSIONS })
})

router.get('/files(/*)?', auth, (req, res) => {
  let path = decodeURI(req.path).slice(7)

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
    let path = decodeURI(req.path).slice(7)
    const { command, folder, name, key } = req.fields

    const needsKey = ['create', 'delete', 'rename', 'upload'].includes(command)
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

        const unsupported = files
          .map(f => f.name)
          .filter(f => {
            const ext = f.split('.').pop().toLowerCase()
            const extensions = [].concat(...Object.values(Vault.EXTENSIONS))
            return !extensions.includes(ext)
          })

        if (unsupported.length) {
          const msg = 'Format not supported: ' + unsupported.join(', ')
          throw new HTTPError(400, msg)
        }

        let failed = []
        const uploads = files.map(async file => {
          let name = file.name
          const split = name.split('.')
          const ext = split.pop().toLowerCase()
          const base = split.join('.')
          name = `${base}.${ext}`

          let data = fs.readFileSync(file.path)
          if (Vault.EXTENSIONS.converted.includes(ext)) {
            const body = new FormData()
            body.append('files', data, name)

            const url = config.CONVERTER_URL + '/convert/office'
            data = await fetch(url, { method: 'POST', body })
              .then(res => res.buffer())
              .catch(() => {
                failed.push(name)
              })
            name = base + '.pdf'
          }

          if (data) {
            Vault.addFile(path, name, data, key)
          }
        })

        await Promise.all(uploads)
        return res.success(failed.length ? { failed } : {})

      case 'verify':
        const success = Vault.isKeyValid(path, key)
        return res.success({ success })

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
