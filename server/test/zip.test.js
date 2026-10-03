const assert = require('assert')
const { execFileSync } = require('child_process')
const fs = require('fs')
const os = require('os')
const ospath = require('path')
const test = require('node:test')

// the vault lives under $HOME, so point it at a scratch folder before loading
const HOME = fs.mkdtempSync(ospath.join(os.tmpdir(), 'vault-test-'))
process.env.HOME = HOME
process.on('exit', () => fs.rmSync(HOME, { recursive: true, force: true }))
require('module-alias')(ospath.join(__dirname, '..'))

const FormData = require('form-data')
const fetch = require('node-fetch')
const app = require('@/app')
const Vault = require('@/services/vault-manager')
const Zip = require('@/services/zip')

const SHARED = ospath.join(Vault.FILES_DIR, 'shared')
const write = (path, text) => {
  const abs = ospath.join(SHARED, path)
  fs.mkdirSync(ospath.dirname(abs), { recursive: true })
  fs.writeFileSync(abs, text)
}

write('proj/a.pdb', 'ATOM a')
write('proj/sub/b.cif', 'data_b')
write('proj/.hidden', 'x')
write('proj/secret/c.sdf', 'c')
write('proj/locked/d.pdb', 'd')
fs.mkdirSync(ospath.join(SHARED, 'proj/empty'))
Vault.encryptFolder('shared/proj/locked', 'pw')

// write a plan's zip to disk the way the route streams it to a response
const zipToFile = plan =>
  new Promise((resolve, reject) => {
    const file = ospath.join(HOME, `${Math.random()}.zip`)
    const out = fs.createWriteStream(file)
    out.setHeader = () => {}
    out.on('close', () => resolve(file))
    out.on('error', reject)
    Zip.send(plan, out)
  })

const names = file =>
  execFileSync('unzip', ['-Z1', file], { encoding: 'utf8' })
    .trim()
    .split('\n')
const read = (file, name) =>
  execFileSync('unzip', ['-p', file, name], { encoding: 'utf8' })

test('a folder zips under its own name, empty folders kept, hidden and locked left out', async () => {
  const plan = Zip.plan('shared/proj/', [], undefined, '')
  assert.strictEqual(plan.name, 'proj.zip')
  assert.deepStrictEqual(plan.skipped, ['proj/locked/'])
  assert.strictEqual(plan.files, 3)

  const file = await zipToFile(plan)
  assert.deepStrictEqual(names(file).sort(), [
    'proj/a.pdb',
    'proj/empty/',
    'proj/secret/c.sdf',
    'proj/sub/b.cif'
  ])
  assert.strictEqual(read(file, 'proj/sub/b.cif'), 'data_b')
})

test('the name field renames the top folder', () => {
  const plan = Zip.plan('shared/proj/', [], undefined, 'my project')
  assert.strictEqual(plan.name, 'my project.zip')
  assert.ok(plan.entries.every(e => e.name.startsWith('my project/')))
})

test('selected items keep their paths relative to the folder', async () => {
  const plan = Zip.plan('shared/proj/', ['a.pdb', 'sub/', 'locked/'])
  assert.strictEqual(plan.name, 'proj.zip')
  assert.deepStrictEqual(plan.skipped, ['locked/'])

  const file = await zipToFile(plan)
  assert.deepStrictEqual(names(file).sort(), ['a.pdb', 'sub/b.cif'])
})

test('one selected folder names the zip after it', () => {
  assert.strictEqual(Zip.plan('shared/proj/', ['sub/']).name, 'sub.zip')
})

test('an encrypted folder is decrypted with its key', async () => {
  const plan = Zip.plan('shared/proj/locked/', [], 'pw')
  const file = await zipToFile(plan)
  assert.deepStrictEqual(names(file), ['locked/d.pdb'])
  assert.strictEqual(read(file, 'locked/d.pdb'), 'd')
})

test('items outside the folder, hidden items and the vault root are refused', () => {
  const status = fn => {
    try {
      fn()
    } catch (e) {
      return e.status
    }
    return 'no error'
  }
  assert.strictEqual(
    status(() => Zip.plan('shared/proj/', ['../a.pdb'])),
    400
  )
  assert.strictEqual(
    status(() => Zip.plan('shared/proj/', ['sub/../../x'])),
    400
  )
  assert.strictEqual(
    status(() => Zip.plan('shared/proj/', ['/etc/passwd'])),
    400
  )
  assert.strictEqual(
    status(() => Zip.plan('shared/proj/', ['.hidden'])),
    400
  )
  assert.strictEqual(
    status(() => Zip.plan('shared/proj/', ['missing.pdb'])),
    404
  )
  assert.strictEqual(
    status(() => Zip.plan('', [])),
    403
  )
  assert.strictEqual(
    status(() => Zip.plan('shared/proj/locked/', ['d.pdb', 'x/..'])),
    400
  )
})

test('the shared folder is not zipped whole, but a selection in it is', () => {
  assert.throws(
    () => Zip.plan('shared/', []),
    e => e.status === 400 && /not zipped whole/.test(e.message)
  )
  const plan = Zip.plan('shared/', ['proj/sub/'])
  assert.strictEqual(plan.name, 'sub.zip')
  assert.deepStrictEqual(plan.entries.map(e => e.name), ['proj/sub/b.cif'])
})

test('a selection of only locked folders is refused', () => {
  assert.throws(
    () => Zip.plan('shared/proj/', ['locked/']),
    /Nothing to download/
  )
})

test('a zip id works once', () => {
  const id = Zip.create({ name: 'x.zip' })
  assert.match(id, /^[0-9a-f]{32}$/)
  assert.deepStrictEqual(Zip.take(id), { name: 'x.zip' })
  assert.strictEqual(Zip.take(id), null)
})

test('the zip command and route work over HTTP', async () => {
  const server = app.listen(0)
  const base = `http://127.0.0.1:${server.address().port}`
  try {
    const info = await fetch(`${base}/info`).then(r => r.json())
    assert.deepStrictEqual(info.nanome2, {
      url: 'https://app.nanome.ai',
      toolId: '01M32ZZKF3RPH80EBW73T2VVKZ'
    })

    const body = new FormData()
    body.append('command', 'zip')
    body.append('items', JSON.stringify(['a.pdb', 'sub/']))
    const started = await fetch(`${base}/files/shared/proj/`, {
      method: 'POST',
      body
    }).then(r => r.json())
    assert.strictEqual(started.success, true)
    assert.strictEqual(started.name, 'proj.zip')
    assert.strictEqual(started.files, 2)

    const res = await fetch(`${base}/zip/${started.id}/${started.name}`)
    assert.strictEqual(res.status, 200)
    assert.strictEqual(res.headers.get('content-type'), 'application/zip')
    assert.match(res.headers.get('content-disposition'), /filename="proj.zip"/)
    const file = ospath.join(HOME, 'http.zip')
    fs.writeFileSync(file, await res.buffer())
    assert.deepStrictEqual(names(file).sort(), ['a.pdb', 'sub/b.cif'])

    const again = await fetch(`${base}/zip/${started.id}/${started.name}`)
    assert.strictEqual(again.status, 404)

    // a locked folder needs its key before anything is planned
    const locked = new FormData()
    locked.append('command', 'zip')
    const refused = await fetch(`${base}/files/shared/proj/locked/`, {
      method: 'POST',
      body: locked
    })
    assert.strictEqual(refused.status, 403)
  } finally {
    server.close()
  }
})
