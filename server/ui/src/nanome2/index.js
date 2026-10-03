// Open in Nanome 2, from this page. MARA and the Workspace API accept requests
// from any origin, so the Vault server takes no part in it.
//
// - Structure files are loaded into a new or an existing workspace, the way
//   the Nanome 2 web app loads them: one file per request, then its default
//   components (without those an entry shows nothing).
// - v1 sessions (.nanome / .nanoscenes) are converted with the Nanome 2
//   importer tool on MARA into a new workspace, which is then read back and
//   checked. pipeline.js does that. It started as the import code of the Open
//   in Nanome 2 Chrome extension this replaces (nanome-ai/open-in-nanome-2
//   a41260f, retired, where the tests of that version are) and has changed
//   since: it reads the bonds of PDB and mmCIF files the way Nanome 2 does,
//   brings a session's images along, makes an empty workspace of a session
//   with nothing Nanome 2 can show, waits for the entry of a load Nanome 2
//   dropped, and asks again for a workspace Nanome 2 refused to create. This
//   repo is public, so the file leaves out references to private Nanome 2
//   source files.
import API from '@/api'

export const SESSION_FILE = /\.(nanome|nanoscenes)$/i

// formats the Nanome 2 web app loads as structures that Vault also stores
// (it has no .mol2 loader)
export const STRUCTURE_FILE = /\.(pdb|pqr|cif|mmcif|sdf|xyz)$/i

// progress steps in the order each kind of job reports them
export const SESSION_STEPS = [
  'vault',
  'token',
  'info',
  'tool',
  'convert',
  'outputs',
  'download',
  'check',
  'workspace',
  'load',
  'scene',
  'components',
  'frames',
  'annotations',
  'images',
  'view',
  'verify',
  'cleanup',
  'done'
]
export const STRUCTURE_STEPS = ['vault', 'token', 'workspace', 'load', 'done']

// the import code is only fetched the first time someone uses it
const loadPipeline = () =>
  import(/* webpackChunkName: "nanome2" */ './pipeline')

const trimSlash = url => String(url || '').replace(/\/+$/, '')

// MARA and the Workspace API check a login with the accounts API MARA names in
// /api/info. Vault logs in at api.nanome.ai, so make sure that API takes it
// before changing anything. Returns MARA's /api/info and the account the login
// belongs to: what Vault creates lands there, and app.nanome.ai only shows it
// when logged in as the same account.
async function checkLogin(ImportFailure, url, token) {
  let info
  try {
    info = await fetch(`${url}/api/info`).then(res => res.json())
  } catch (e) {
    throw new ImportFailure('token', `could not reach Nanome 2 at ${url}`)
  }

  const accounts = trimSlash(info.accounts_api_url)
  if (!accounts) return { info, account: null }

  const res = await fetch(`${accounts}/user/session`, {
    headers: { Authorization: `Bearer ${token}` }
  }).catch(() => null)
  const body = res && (await res.json().catch(() => null))
  if (!body || !body.success) {
    throw new ImportFailure(
      'token',
      `Nanome 2 did not accept your Vault login (checked at ${accounts}). ` +
        'Log out of Vault, log in again and retry.',
      { status: res && res.status, body: JSON.stringify(body) }
    )
  }

  const user = (body.results && body.results.user) || {}
  return { info, account: user.email || user.name || user.unique || null }
}

// reports the account in the progress, for the card to show
async function checkLoginWithProgress(ImportFailure, url, token, onProgress) {
  onProgress({ step: 'token', message: 'Checking your login with Nanome 2' })
  const login = await checkLogin(ImportFailure, url, token)
  if (login.account) {
    const message = `Using the Nanome 2 account ${login.account}`
    onProgress({ step: 'token', message, account: login.account })
  }
  return login
}

// JSON requests to the Workspace API, sent the way the web app sends them
function workspaceApi(ImportFailure, info, token) {
  const base = trimSlash(info.workspace_api_url)
  if (!base) {
    throw new ImportFailure('token', 'Nanome 2 names no Workspace API')
  }

  return async (step, method, path, { json, form } = {}) => {
    const headers = { Authorization: `Bearer ${token}` }
    let body = form
    if (!form && method !== 'GET') {
      headers['Content-Type'] = 'application/json'
      if (json !== undefined) body = JSON.stringify(json)
    }

    const url = base + path
    let res
    try {
      res = await fetch(url, { method, headers, body })
    } catch (e) {
      throw new ImportFailure(step, `${method} ${url} failed: ${e.message}`)
    }

    const text = await res.text()
    if (!res.ok) {
      const message = `${method} ${url} returned HTTP ${res.status}`
      throw new ImportFailure(step, message, { status: res.status, body: text })
    }
    try {
      return text ? JSON.parse(text) : null
    } catch (e) {
      const message = `${method} ${url} did not return JSON`
      throw new ImportFailure(step, message, { body: text })
    }
  }
}

// the account's workspaces, most recently opened first, as the web app lists
// them: {account, workspaces}
export async function listWorkspaces({ token, url }) {
  const { ImportFailure } = await loadPipeline()
  const { info, account } = await checkLogin(ImportFailure, url, token)
  const request = workspaceApi(ImportFailure, info, token)
  const list = await request('workspaces', 'GET', '/workspaces')

  const opened = w => new Date(w.lastAccessedAt || w.updatedAt || 0)
  const workspaces = (Array.isArray(list) ? list : [])
    .filter(w => w && w.id)
    .sort((a, b) => opened(b) - opened(a))
  return { account, workspaces }
}

// loads structure files into `workspace` ({id, name}), or into a new
// workspace called `name` when there is none
export async function loadStructures(options) {
  const { paths, token, url, workspace, name, onProgress } = options
  const { ImportFailure, retryConcurrency } = await loadPipeline()
  const counter = i => (paths.length > 1 ? ` (${i + 1}/${paths.length})` : '')

  const files = []
  for (const [i, path] of paths.entries()) {
    const filename = path.split('/').pop()
    onProgress({
      step: 'vault',
      message: `Reading ${filename} from Vault${counter(i)}`
    })
    try {
      files.push({ name: filename, bytes: await API.getFileBytes(path) })
    } catch (e) {
      throw new ImportFailure('vault', `${filename}: ${e.message}`)
    }
  }

  const { info } = await checkLoginWithProgress(
    ImportFailure,
    url,
    token,
    onProgress
  )
  const request = workspaceApi(ImportFailure, info, token)

  const partial = {}
  const entries = []
  try {
    let target = workspace
    if (!target) {
      onProgress({ step: 'workspace', message: `Creating workspace "${name}"` })
      const description = `Loaded from Nanome Vault: ${files
        .map(f => f.name)
        .join(', ')}`
      // Nanome 2 refuses a creation that runs into another change to the
      // account's workspaces, and creates nothing: ask again
      target = await retryConcurrency(
        () =>
          request('workspace', 'POST', '/workspaces', {
            json: { name, description }
          }),
        {
          onRetry: (n, limit) =>
            onProgress({
              step: 'workspace',
              message:
                "Nanome 2 was changing this account's workspaces and " +
                `created none; asking again (${n} of ${limit})`
            })
        }
      )
      if (!target || !target.id) {
        throw new ImportFailure(
          'workspace',
          'the Workspace API returned no workspace id',
          {
            body: JSON.stringify(target)
          }
        )
      }
    }

    const id = encodeURIComponent(target.id)
    partial.workspaceUrl = `${url}/workspaces/${id}`

    // the web app adds to the scene its viewer is on; here that is the first
    onProgress({ step: 'workspace', message: `Opening "${target.name}"` })
    const scenes = await request('workspace', 'GET', `/workspaces/${id}/scenes`)
    const scene = (Array.isArray(scenes) ? scenes : [])
      .filter(s => s && Number.isInteger(s.serial))
      .sort((a, b) => a.serial - b.serial)[0]
    if (!scene) {
      throw new ImportFailure('workspace', 'the workspace has no scene', {
        body: JSON.stringify(scenes)
      })
    }

    for (const [i, file] of files.entries()) {
      onProgress({ step: 'load', message: `Loading ${file.name}${counter(i)}` })
      const form = new FormData()
      form.append('files', new Blob([file.bytes]), file.name)
      const loaded = await request(
        'load',
        'POST',
        `/workspaces/${id}/entries/load-multiple`,
        {
          form
        }
      )

      for (const entry of Array.isArray(loaded) ? loaded : []) {
        const path = `/workspaces/${id}/scenes/${scene.serial}/entries/${entry.serial}/components/add-default`
        await request('load', 'POST', path)
        entries.push({
          serial: entry.serial,
          name: entry.name,
          file: file.name
        })
      }
      partial.entries = entries.slice()
    }

    onProgress({
      step: 'done',
      message: `Workspace ready: ${partial.workspaceUrl}`
    })
    return {
      url: partial.workspaceUrl,
      workspaceName: target.name,
      existing: !!workspace,
      entries
    }
  } catch (e) {
    const failure =
      e instanceof ImportFailure
        ? e
        : new ImportFailure('load', e.message || String(e))
    failure.partial = partial
    throw failure
  }
}

export async function openInNanome2({ path, token, url, toolId, onProgress }) {
  const { ImportFailure, runImport } = await loadPipeline()
  const filename = path.split('/').pop()

  onProgress({ step: 'vault', message: `Reading ${filename} from Vault` })
  let bytes
  try {
    bytes = await API.getFileBytes(path)
  } catch (e) {
    throw new ImportFailure('vault', e.message)
  }

  await checkLoginWithProgress(ImportFailure, url, token, onProgress)

  // 'done' waits until MARA's copy of the session is deleted
  let done = null
  const progress = event => {
    if (event.step === 'done') done = event
    else onProgress(event)
  }

  let result
  try {
    result = await runImport({
      bytes,
      filename,
      token,
      maraUrl: url,
      toolId,
      onProgress: progress
    })
  } catch (e) {
    const id = e.partial && e.partial.toolRunId
    if (id) {
      await deleteToolRun(url, token, id, onProgress).catch(() => {
        e.message += ` MARA keeps its copy of the session (tool run ${id}).`
      })
    }
    throw e
  }

  // MARA keeps each tool run, the uploaded session and everything converted
  // from it, until the run is deleted. Vault has the session, so the run goes.
  // First the one output the workspace does not take in, v1's metadata in
  // full, is downloaded for the card to offer; if that fails, the run stays.
  const run = result.toolRun
  if (run) {
    try {
      result.metadata = await downloadMetadata(url, token, run, onProgress)
      await deleteToolRun(url, token, run.id, onProgress)
      run.deleted = true
    } catch (e) {
      result.warnings.push(
        `MARA keeps its copy of the session (tool run ${run.id}): ${e.message}`
      )
    }
  }
  if (done) onProgress(done)
  return result
}

const toolRunUrl = (url, id) =>
  `${trimSlash(url)}/api/tools/runs/${encodeURIComponent(id)}`

async function maraRequest(method, url, token) {
  const res = await fetch(url, {
    method,
    headers: { Authorization: `Bearer ${token}` }
  })
  if (!res.ok) throw new Error(`${method} ${url} returned HTTP ${res.status}`)
  return res
}

// the run's *_metadata.json as {name, text}, or null when it has none
async function downloadMetadata(url, token, run, onProgress) {
  const name = (run.files || []).find(f => f.endsWith('_metadata.json'))
  if (!name) return null
  onProgress({ step: 'cleanup', message: `Downloading ${name}` })
  const file = `${toolRunUrl(url, run.id)}/${encodeURIComponent(name)}`
  const res = await maraRequest('GET', file, token)
  return { name, text: await res.text() }
}

async function deleteToolRun(url, token, id, onProgress) {
  onProgress({
    step: 'cleanup',
    message: `Deleting MARA's copy of the session (tool run ${id})`
  })
  await maraRequest('DELETE', toolRunUrl(url, id), token)
}
