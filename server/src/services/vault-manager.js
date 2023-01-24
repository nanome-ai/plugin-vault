const fs = require('fs-extra')
const moment = require('moment')
const os = require('os')
const ospath = require('path')
const walk = require('@nodelib/fs.walk')

const aes = require('./aes-cipher')
const config = require('@/config')
const du = require('@/utils/du')
const { HTTPError } = require('@/utils/error')

// walk settings to find all files not starting with '.'
const WALK_SETTINGS = new walk.Settings({
  entryFilter: e => !e.name.startsWith('.') && e.dirent.isFile()
})

const LOCK_TEXT = 'nanome-vault-lock'
const FILES_DIR = ospath.join(os.homedir(), 'Documents/nanome-vault')
const UPLOADS_DIR = ospath.join(os.tmpdir(), 'nanome-vault')
// fs.ensureDirSync(UPLOADS_DIR)

const SHARED_DIR = ospath.join(FILES_DIR, 'shared')
// fs.ensureDirSync(SHARED_DIR)

// prettier-ignore
exports.EXTENSIONS = {
  supported: ['pdb', 'sdf', 'cif', 'pdf', 'png', 'jpg', 'nanome', 'nanosr', 'lua', 'obj'],
  extras: ['ccp4', 'dcd', 'dsn6', 'dx', 'gro', 'mae', 'mmcif', 'moe', 'mol2', 'pqr', 'pse', 'psf', 'smiles', 'trr', 'xtc', 'xyz'],
  converted: ['ppt', 'pptx', 'doc', 'docx', 'txt', 'rtf', 'odt', 'odp'],
  external: ['map', 'map.gz']
}

exports.ALL_EXTENSIONS = [].concat(...Object.values(exports.EXTENSIONS))

exports.FILES_DIR = FILES_DIR
exports.UPLOADS_DIR = UPLOADS_DIR

// add data to vault at path/filename, where filename can contain a path
exports.addFile = (path, filename, data, key) => {
  exports.checkStorageLimit(path, data.length)

  if (key !== undefined) {
    data = aes.encrypt(data, key)
  }

  // create folder paths
  path = exports.getVaultPath(path, false)
  const subFolder = ospath.join(path, ospath.dirname(filename))
  // fs.ensureDirSync(subFolder)

  // rename on duplicates: file.txt -> file (n).txt
  const regex = /^(.+[/\\])([^/\\]+?)(?: \((\d+)\))?(\.\w+)$/
  let filePath = ospath.join(path, filename)
  let [, dir, name, copy, ext] = regex.exec(filePath)
  if (copy === undefined) copy = 1

  while (fs.existsSync(filePath)) {
    filePath = `${dir}${name} (${++copy})${ext}`
  }

  fs.writeFileSync(filePath, data)
}

// throws error if size exceeds user storage limit
exports.checkStorageLimit = (path, size) => {
  const match = /^(user-[0-9a-f]{8})/.exec(path)
  if (match && config.USER_STORAGE) {
    const userPath = exports.getVaultPath(match[1], false)
    if (du(userPath) + size > config.USER_STORAGE) {
      const msg = `User storage exceeded (max ${config.USER_STORAGE_MSG})`
      throw new HTTPError(413, msg)
    }
  }
}

// creates a path or throws if path exists
exports.createPath = path => {
  path = exports.getVaultPath(path, false)
  if (fs.existsSync(path)) {
    throw new HTTPError(400, 'Path already exists')
  }
  fs.mkdirSync(path, { recursive: true })
}

// decrypts data with key and writes result to outPath, or returns if no outPath
exports.decryptData = (data, key, outPath) => {
  const dec = aes.decrypt(data, key)
  if (!outPath) return dec
  fs.writeFileSync(outPath, dec)
}

// decrypts full contents of path or throws false if key invalid
exports.decryptFolder = (path, key) => {
  path = exports.getVaultPath(path)

  if (!exports.isPathLocked(path)) {
    throw new HTTPError(400, 'Path is not locked')
  }
  if (!exports.isKeyValid(path, key)) {
    throw new HTTPError(400, 'Key is not valid')
  }

  // decrypt all files not starting with '.'
  const files = walk.walkSync(path, WALK_SETTINGS)
  for (const file of files) {
    const data = fs.readFileSync(file.path)
    exports.decryptData(data, key, file.path)
  }

  // remove lock file
  const lock = ospath.join(path, '.locked')
  fs.removeSync(lock)
}

// deletes a path
exports.deletePath = path => {
  if (!path || path === 'shared') {
    throw HTTPError.FORBIDDEN
  }

  path = exports.getVaultPath(path)
  fs.removeSync(path)
}

// encrypts data with key and writes result to outPath, or returns if no outPath
exports.encryptData = (data, key, outPath) => {
  const enc = aes.encrypt(data, key)
  if (!outPath) return enc
  fs.writeFileSync(outPath, enc)
}

// encrypts full contents of path or throws if encrypted subfolder exists
exports.encryptFolder = (path, key) => {
  path = exports.getVaultPath(path)

  // check if subfolder already encrypted
  if (walk.walkSync(path).find(f => f.name === '.locked')) {
    throw new HTTPError(400, 'Path already encrypted')
  }

  // encrypt all files not starting with '.'
  const files = walk.walkSync(path, WALK_SETTINGS)
  for (const file of files) {
    const data = fs.readFileSync(file.path)
    exports.encryptData(data, key, file.path)
  }

  // add lock file for key verification
  const lock = ospath.join(path, '.locked')
  const data = aes.encrypt(LOCK_TEXT, key)
  fs.writeFileSync(lock, data)
}

// returns file data of path, decrypted with key if exists
exports.getFile = (path, key) => {
  path = exports.getVaultPath(path)
  let data = fs.readFileSync(path)

  if (key !== undefined) {
    data = exports.decryptData(data, key)
  }

  return data
}

// return encryption root of path, or null if not encrypted
exports.getLockedPath = path => {
  if (path.startsWith(FILES_DIR)) {
    path = path.slice(FILES_DIR.length)
  }

  const parts = path.split(ospath.sep)
  let subPath = ''
  for (const part of parts) {
    subPath = ospath.join(subPath, part)
    path = ospath.join(FILES_DIR, subPath)

    if (fs.existsSync(ospath.join(path, '.locked'))) {
      return subPath + ospath.sep
    }
  }

  return null
}

// return full path of item in vault
exports.getVaultPath = (subPath, enforceExists) => {
  const path = ospath.join(FILES_DIR, subPath || '')
  if (!exports.isSafePath(path, undefined, enforceExists)) {
    throw HTTPError.NOT_FOUND
  }

  return path
}

// returns true if key is correct to decrypt
exports.isKeyValid = (path, key) => {
  path = exports.getLockedPath(path)
  if (path === null) return true

  try {
    const lock = ospath.join(FILES_DIR, path, '.locked')
    const enc = fs.readFileSync(lock)
    const dec = aes.decrypt(enc, key)
    return dec.toString() === LOCK_TEXT
  } catch (e) {
    return false
  }
}

// returns true if folder encrypted
exports.isPathLocked = path => {
  return exports.getLockedPath(path) !== null
}

// return true if path in vault and exists
exports.isSafePath = (subPath, basePath = FILES_DIR, enforceExists = true) => {
  const safePath = ospath.normalize(basePath.replace('~', os.homedir()))
  const path = ospath.resolve(basePath, subPath)
  const isSafe = !ospath.relative(safePath, path).startsWith('..')
  const exists = fs.existsSync(path)
  return isSafe && (!enforceExists || exists)
}

// list files, folders, and locked folders in path
exports.listPath = path => {
  path = exports.getVaultPath(path)

  const result = {
    locked_path: exports.getLockedPath(path),
    locked: [],
    folders: [],
    files: []
  }

  // return only 'shared' folder for root
  if (path === FILES_DIR) {
    result.folders.push({
      name: 'shared',
      size: '',
      size_text: '',
      created: '',
      created_text: ''
    })
    return result
  }

  const items = fs
    .readdirSync(path)
    .filter(f => !f.startsWith('.'))
    .sort((a, b) => (a.toLowerCase() < b.toLowerCase() ? -1 : 1))

  for (const item of items) {
    const itemPath = ospath.join(path, item)
    const stats = fs.statSync(itemPath)
    const isDir = stats.isDirectory()

    const bytes = isDir ? du(itemPath) : stats.size
    const power = bytes && Math.floor(Math.log(bytes) / Math.log(1024))
    const unit = ['B', 'KB', 'MB', 'GB'][power]
    const size = `${(bytes / 1024 ** power).toFixed(1)}${unit}`

    // using mtime for created because ctime not accurate
    result[isDir ? 'folders' : 'files'].push({
      name: item,
      size: bytes,
      size_text: size,
      created: stats.mtime
        .toISOString()
        .replace('T', ' ')
        .replace(/:[^:]+$/, ''),
      created_text: moment(stats.mtime).fromNow()
    })

    const lockPath = ospath.join(itemPath, '.locked')
    if (isDir && fs.existsSync(lockPath)) {
      result.locked.push(item)
    }
  }

  return result
}

// moves a file/folder to folder
exports.movePath = (path, folder) => {
  const oldPath = exports.getVaultPath(path)
  const base = ospath.basename(oldPath)
  const destPath = exports.getVaultPath(folder, false)
  const newPath = ospath.join(destPath, base)

  if (fs.existsSync(newPath)) {
    throw new HTTPError(400, 'Item already exists at destination')
  }

  fs.renameSync(oldPath, newPath)
}

// renames a file/folder at path
exports.renamePath = (path, name) => {
  const oldPath = exports.getVaultPath(path)
  const dir = ospath.dirname(oldPath)
  const newPath = ospath.join(dir, name)

  if (fs.existsSync(newPath)) {
    throw new HTTPError(400, 'Path already exists')
  }

  fs.renameSync(oldPath, newPath)
}
