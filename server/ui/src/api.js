import store from '@/store'
const AUTH_API = 'https://api.nanome.ai'

function replacePath(path) {
  return path
    .replace(/^\/account($|\/)/, `/${store.state.unique}$1`)
    .replace(/^\/my-org($|\/)/, `/${store.state.org}$1`)
    .replace(/[#?]/g, '_')
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

  async download(path) {
    const options = { headers: {} }
    const key = API.keys.get(path)
    if (key) {
      options.headers['Vault-Key'] = key
    }

    if (store.state.token) {
      options.headers['Authorization'] = 'Bearer ' + store.state.token
    }

    path = replacePath(path)
    const blob = await fetch('/files' + path, options).then(res => res.blob())

    const a = document.createElement('a')
    const url = URL.createObjectURL(blob)
    a.href = url
    a.download = path.substring(path.lastIndexOf('/') + 1)
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
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
