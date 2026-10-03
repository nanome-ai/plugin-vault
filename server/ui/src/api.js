import store from '@/store'
const AUTH_API = 'https://api.nanome.ai'

function replacePath(path) {
  return path
    .replace(/^\/account($|\/)/, `/${store.state.unique}$1`)
    .replace(/^\/my-org($|\/)/, `/${store.state.org}$1`)
    .replace(/[#?]/g, '_')
}

function saveAs(href, filename) {
  const a = document.createElement('a')
  a.href = href
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
}

function addSlash(path) {
  return path.replace(/\b$/, '/')
}

async function request(url, options = {}) {
  if (store.state.token && !url.startsWith(AUTH_API)) {
    options.headers = Object.assign({}, options.headers, {
      Authorization: 'Bearer ' + store.state.token
    })
  }
  const res = await fetch(url, options)
  const json = await res.json()
  json.code = res.status
  return json
}

function sendCommand(path, command, params = {}) {
  if (!params.key) {
    params.key = API.keys.get(path)
  }
  path = replacePath(path)

  const data = new FormData()
  data.append('command', command)

  for (const key in params) {
    const value = params[key]
    if (value instanceof Array) {
      for (const item of value) {
        data.append(key, item)
      }
    } else if (value) {
      data.append(key, value)
    }
  }

  return request('/files' + path, {
    method: 'POST',
    body: data
  })
}

const keys = {}

const API = {
  keys: {
    add(path, key) {
      path = addSlash(path)
      keys[path] = key
    },
    get(path) {
      path = addSlash(path)
      const paths = Object.keys(keys)
      const locked = paths.find(p => path.indexOf(p) == 0)
      return keys[locked]
    },
    remove(path) {
      path = addSlash(path)
      delete keys[path]
    }
  },

  getInfo() {
    return request('/info')
  },

  login({ username, password, tfa_code }) {
    const body = {
      login: username,
      pass: password,
      tfa_code,
      source: 'web:plugin-vault'
    }

    return request(`${AUTH_API}/user/login`, {
      headers: { 'Content-Type': 'application/json' },
      method: 'POST',
      body: JSON.stringify(body)
    })
  },

  loginSSO(email, redirect) {
    const params = new URLSearchParams({
      email,
      redirect,
      cookie: false
    })

    return request(`${AUTH_API}/sso/login?` + params, {
      headers: { 'Content-Type': 'application/json' },
      method: 'GET'
    })
  },

  refresh() {
    const token = store.state.token
    if (!token) return {}

    return request(`${AUTH_API}/user/session`, {
      headers: { Authorization: `Bearer ${token}` }
    })
  },

  fetchFile(path) {
    const options = { headers: {} }
    const key = API.keys.get(path)
    if (key) {
      options.headers['Vault-Key'] = key
    }

    if (store.state.token) {
      options.headers['Authorization'] = 'Bearer ' + store.state.token
    }

    return fetch('/files' + replacePath(path), options)
  },

  async download(path) {
    const blob = await API.fetchFile(path).then(res => res.blob())
    const url = URL.createObjectURL(blob)
    saveAs(
      url,
      replacePath(path)
        .split('/')
        .pop()
    )
    URL.revokeObjectURL(url)
  },

  async getFileBytes(path) {
    const res = await API.fetchFile(path)
    if (!res.ok) {
      const why = {
        401: 'Vault did not accept your login, please log in again',
        403: 'Vault refused the file; is the folder key still unlocked?',
        404: 'Vault has no such file; was it renamed or moved?'
      }
      throw new Error(why[res.status] || `Vault returned HTTP ${res.status}`)
    }
    return res.arrayBuffer()
  },

  // items: names inside the folder at path; none zips the folder itself
  zip(path, items = [], name) {
    return sendCommand(path, 'zip', { items: JSON.stringify(items), name })
  },

  // the browser streams the zip to disk itself
  downloadZip({ id, name }) {
    saveAs(`/zip/${id}/${encodeURIComponent(name)}`, name)
  },

  list(path) {
    const options = { headers: {} }
    const key = API.keys.get(path)
    if (key) {
      options.headers['Vault-Key'] = key
    }

    path = replacePath(path)
    return request('/files' + path, options)
  },

  async getFolder(path) {
    const folder = {
      path: '',
      parent: '',
      folders: [],
      locked: [],
      files: []
    }

    if (path.slice(-1) !== '/') {
      path += '/'
    }

    if (path !== '/') {
      const lastSlash = path.slice(0, -1).lastIndexOf('/')
      folder.parent = path.substring(0, lastSlash) + '/'
    }

    const data = await API.list(path)
    if (!data.success) {
      const err = new Error(data.error)
      err.code = data.code
      throw err
    }

    folder.path = path
    folder.locked_path = data.locked_path
    folder.locked = data.locked
    folder.folders = data.folders
    folder.files = data.files.map(f => {
      const [full, name, ext = ''] = /^(.+?)(?:\.(\w+))?$/.exec(f.name)
      return { full, name, ext, size_text: f.size_text }
    })

    return folder
  },

  upload(path, files, onProgress) {
    if (!files || !files.length) return

    const data = new FormData()
    data.append('command', 'upload')

    const key = API.keys.get(path)
    if (key) {
      data.append('key', key)
    }

    for (const file of files) {
      data.append('files', file)
    }

    const request = new XMLHttpRequest()
    const cancel = () => request.abort()

    const promise = new Promise((resolve, reject) => {
      request.open('POST', '/files' + replacePath(path), true)
      request.upload.addEventListener('progress', onProgress)

      if (store.state.token) {
        request.setRequestHeader('Authorization', 'Bearer ' + store.state.token)
      }

      request.addEventListener('abort', () => reject())
      request.addEventListener('load', () => {
        const json = JSON.parse(request.responseText)
        json.code = request.status
        resolve(json)
      })
      request.send(data)
    })

    return { promise, cancel }
  },

  uploadInit(path, name, size) {
    return sendCommand(path, 'upload-init', { name, size })
  },

  uploadCancel(id) {
    return sendCommand('', 'upload-cancel', { id })
  },

  uploadChunk({ id, name, chunk, start, end, size, onProgress }) {
    const data = new FormData()
    data.append('command', 'upload-chunk')
    data.append('chunk', chunk)

    const request = new XMLHttpRequest()
    const cancel = () => {
      API.uploadCancel(id)
      request.abort()
    }

    const promise = new Promise((resolve, reject) => {
      request.open('POST', '/files', true)
      request.upload.addEventListener('progress', onProgress)

      request.setRequestHeader('X-Upload-ID', id)
      request.setRequestHeader('X-File-Name', name)
      request.setRequestHeader('Content-Range', `bytes ${start}-${end}/${size}`)

      if (store.state.token) {
        request.setRequestHeader('Authorization', 'Bearer ' + store.state.token)
      }

      request.addEventListener('abort', () => reject())
      request.addEventListener('load', () => {
        const json = JSON.parse(request.responseText)
        json.code = request.status
        resolve(json)
      })
      request.send(data)
    })

    return { promise, cancel }
  },

  move(path, folder) {
    folder = replacePath(folder)
    return sendCommand(path, 'move', { folder })
  },

  delete(path) {
    return sendCommand(path, 'delete')
  },

  create(path) {
    return sendCommand(path, 'create')
  },

  rename(path, name) {
    return sendCommand(path, 'rename', { name })
  },

  encrypt(path, key) {
    return sendCommand(path, 'encrypt', { key })
  },

  decrypt(path, key) {
    return sendCommand(path, 'decrypt', { key })
  },

  verifyKey(path, key) {
    return sendCommand(path, 'verify', { key })
  }
}

export default API
