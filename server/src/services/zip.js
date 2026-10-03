const archiver = require('archiver')
const crypto = require('crypto')
const fs = require('fs-extra')
const ospath = require('path')
const { Readable } = require('stream')

const Vault = require('@/services/vault-manager')
const { HTTPError } = require('@/utils/error')

// zip32 tops out at 4 GB, and a browser holds the whole download meanwhile
const MAX_BYTES = 4 * 1024 ** 3
// a zip is started with POST (authorized) and fetched with GET by id, so the
// browser can stream it to disk; ids are single use and expire quickly
const EXPIRY_MS = 60 * 1000
const PENDING = new Map()

const byName = (a, b) => (a.name.toLowerCase() < b.name.toLowerCase() ? -1 : 1)

const cleanName = name =>
  String(name || '')
    .replace(/[\\/:*?"<>|\u0000-\u001f\u007f]/g, '_')
    .trim()

// resolve an item relative to base, refusing anything outside it or hidden
const resolveItem = (base, item) => {
  const clean = item.replace(/[#?]/g, '_').replace(/\/+$/, '')
  const invalid = new HTTPError(400, `Invalid item: "${item}"`)
  if (!clean || ospath.isAbsolute(clean)) throw invalid

  const abs = ospath.resolve(base, clean)
  const rel = ospath.relative(base, abs)
  if (!rel || rel.startsWith('..') || ospath.isAbsolute(rel)) throw invalid

  const parts = rel.split(ospath.sep)
  if (parts.some(p => p.startsWith('.'))) throw invalid
  if (!fs.existsSync(abs)) throw HTTPError.NOT_FOUND

  return { abs, rel: parts.join('/') }
}

const addFile = (plan, abs, name) => {
  plan.entries.push({ path: abs, name })
  plan.bytes += fs.statSync(abs).size
  plan.files++
}

// a folder with its own lock needs its own key, so it is left out
const addFolder = (plan, abs, name) => {
  if (fs.existsSync(ospath.join(abs, '.locked'))) {
    plan.skipped.push(name)
    return
  }
  walk(plan, abs, name)
}

const walk = (plan, dir, prefix) => {
  const children = fs
    .readdirSync(dir, { withFileTypes: true })
    .filter(d => !d.name.startsWith('.'))
    .sort(byName)

  // keep empty folders so the zip matches what Vault shows
  if (!children.length) plan.entries.push({ name: prefix, dir: true })

  for (const child of children) {
    const abs = ospath.join(dir, child.name)
    if (child.isDirectory()) addFolder(plan, abs, `${prefix}${child.name}/`)
    else if (child.isFile()) addFile(plan, abs, prefix + child.name)
  }
}

// what a zip of `items` in folder `path` holds. With no items, the folder
// itself is zipped under a top folder called `name`.
exports.plan = (path, items = [], key, name) => {
  const base = Vault.getVaultPath(path)
  const root = ospath.resolve(Vault.FILES_DIR)
  if (ospath.resolve(base) === root) {
    throw HTTPError.FORBIDDEN
  }
  // the file explorer does not offer it either (400: a 403 asks for a key)
  if (!items.length && ospath.resolve(base) === ospath.join(root, 'shared')) {
    throw new HTTPError(
      400,
      "The shared folder holds everyone's files, so it is not zipped whole: " +
        'select what to download in it'
    )
  }
  if (!fs.statSync(base).isDirectory()) {
    throw new HTTPError(400, 'Not a folder')
  }

  const plan = {
    name: '',
    entries: [],
    skipped: [],
    files: 0,
    bytes: 0,
    // files under a locked folder are stored encrypted with its key
    key: Vault.isPathLocked(path) ? key : undefined
  }

  const folderName = cleanName(name) || ospath.basename(base) || 'vault'
  if (!items.length) {
    walk(plan, base, `${folderName}/`)
    plan.name = `${folderName}.zip`
  } else {
    const resolved = items.map(item => resolveItem(base, item))
    for (const { abs, rel } of resolved) {
      if (fs.statSync(abs).isDirectory()) addFolder(plan, abs, `${rel}/`)
      else addFile(plan, abs, rel)
    }
    const single = resolved.length === 1 && ospath.basename(resolved[0].abs)
    plan.name = `${cleanName(name) || single || folderName}.zip`
  }

  if (!plan.entries.length) {
    throw new HTTPError(
      400,
      'Nothing to download: encrypted folders are left out'
    )
  }
  if (plan.bytes > MAX_BYTES) {
    const gb = (plan.bytes / 1024 ** 3).toFixed(1)
    throw new HTTPError(413, `Too large to zip (${gb} GB, max 4 GB)`)
  }

  return plan
}

exports.create = plan => {
  const id = crypto.randomBytes(16).toString('hex')
  const timer = setTimeout(() => PENDING.delete(id), EXPIRY_MS)
  timer.unref()
  PENDING.set(id, { plan, timer })
  return id
}

// returns the plan for id once, or null if unknown or expired
exports.take = id => {
  const job = PENDING.get(id)
  if (!job) return null
  PENDING.delete(id)
  clearTimeout(job.timer)
  return job.plan
}

const contentDisposition = name => {
  const ascii = name.replace(/[^\x20-\x7e]/g, '_').replace(/"/g, "'")
  return `attachment; filename="${ascii}"; filename*=UTF-8''${encodeURIComponent(
    name
  )}`
}

// read and decrypt only when the archive gets to this entry
const decrypted = (path, key) =>
  Readable.from(
    (async function*() {
      yield Vault.decryptData(await fs.readFile(path), key)
    })(),
    { objectMode: false }
  )

exports.send = (plan, res) => {
  const archive = archiver('zip')

  res.setHeader('Content-Type', 'application/zip')
  res.setHeader('Content-Disposition', contentDisposition(plan.name))

  // a file removed since the plan was made is left out
  archive.on('warning', e => console.warn('zip:', e.message))
  archive.on('error', e => {
    console.error('zip:', e)
    res.destroy(e)
  })
  res.on('close', () => {
    if (!res.writableFinished) archive.abort()
  })
  archive.pipe(res)

  for (const entry of plan.entries) {
    if (entry.dir) {
      archive.append(null, { name: entry.name })
    } else if (plan.key !== undefined) {
      archive.append(decrypted(entry.path, plan.key), { name: entry.name })
    } else {
      archive.file(entry.path, { name: entry.name })
    }
  }

  archive.finalize()
}
