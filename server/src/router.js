const express = require('express')
const router = express.Router()

const fs = require('fs')
const ospath = require('path')
const Vault = require('@/services/vault-manager')
const auth = require('@/utils/auth')
const { HTTPError } = require('@/utils/error')

const STATIC_DIR = ospath.resolve('ui/dist')

router.get('/info', (req, res) => {
  res.success({ extensions: Vault.EXTENSIONS })
})

router.use('/files', auth, (req, res) => {
  let path = decodeURI(req.path).slice(1)

  if (req.method === 'GET') {
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
  }

  if (req.method === 'POST') {
    const { command, name, key } = req.fields
    // TODO: validate args

    const needsKey = ['create', 'delete', 'rename', 'upload'].includes(command)
    if (needsKey && !Vault.isKeyValid(path, key)) throw HTTPError.FORBIDDEN

    if (command === 'create') {
      Vault.createPath(path)
    } else if (command === 'delete') {
      Vault.deletePath(path)
    } else if (command === 'rename') {
      Vault.renamePath(path, name)
    } else if (command === 'encrypt') {
      Vault.encryptFolder(path, key)
    } else if (command === 'decrypt') {
      Vault.decryptFolder(path, key)
    } else if (command === 'verify') {
      const success = Vault.isKeyValid(path, key)
      return res.success({ success })
    } else if (command === 'upload') {
      let { files } = req.files
      if (!Array.isArray(files)) files = [files]

      const unsupported = files
        .map(f => f.name)
        .filter(f => {
          const ext = f.split('.').pop()
          const extensions = [].concat(Object.values(Vault.EXTENSIONS))
          return extensions.includes(ext)
        })

      if (unsupported.length) {
        const msg = 'Format not supported: ' + unsupported.join(', ')
        throw new HTTPError(400, msg)
      }

      let failed = []
      for (const file of files) {
        // TODO: convert files
        const data = fs.readFileSync(file.path)
        Vault.addFile(path, file.name, data, key)
      }

      const result = failed.length ? { failed } : {}
      return res.success(result)
    } else {
      throw new HTTPError(400, 'Invalid command')
    }

    res.success()
  }
})

router.use(express.static(STATIC_DIR))
router.get('*', (req, res) => {
  res.sendFile(STATIC_DIR + '/index.html')
})

module.exports = router
