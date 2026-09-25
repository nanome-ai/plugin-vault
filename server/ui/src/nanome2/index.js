// Open in Nanome 2: converts a v1 session (.nanome / .nanoscenes) with the
// Nanome 2 importer tool on MARA, builds a new Nanome 2 workspace from the
// result, reads it back to check it, and returns its link. Everything runs in
// this page: MARA and the Workspace API accept requests from any origin.
//
// pipeline.js is copied from nanome-ai/open-in-nanome-2 (a991347), where it
// is documented and tested. This repo is public, so the copy leaves out the
// upstream comments' references to private Nanome 2 source files; the code is
// the same. Change it there and copy it over the same way.
import API from '@/api'

export const SESSION_FILE = /\.(nanome|nanoscenes)$/i

// progress steps in the order the import reports them
export const STEPS = [
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
  'annotations',
  'verify',
  'cleanup',
  'done'
]

// the import code is only fetched the first time someone uses it
const loadPipeline = () =>
  import(/* webpackChunkName: "nanome2" */ './pipeline')

// MARA and the Workspace API check a login with the accounts API MARA names in
// /api/info. Vault logs in at api.nanome.ai, so make sure that API takes it
// before converting anything.
async function checkLogin(ImportFailure, url, token) {
  let info
  try {
    info = await fetch(`${url}/api/info`).then(res => res.json())
  } catch (e) {
    throw new ImportFailure('token', `could not reach Nanome 2 at ${url}`)
  }

  const accounts = String(info.accounts_api_url || '').replace(/\/+$/, '')
  if (!accounts) return

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

  onProgress({ step: 'token', message: 'Checking your login with Nanome 2' })
  await checkLogin(ImportFailure, url, token)

  return runImport({
    bytes,
    filename,
    token,
    maraUrl: url,
    toolId,
    onProgress
  })
}
