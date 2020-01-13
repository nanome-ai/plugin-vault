import store from '@/store'
const LOGIN_API = 'https://api.nanome.ai/user'

function replaceAccount(path) {
  return path.replace(/^\/account/, '/' + store.state.unique)
}

function request(url, options) {
  return fetch(url, options).then(async res => {
    const json = await res.json()
    json.code = res.status
    return json
  })
}

function sendCommand(path, command, params) {
  path = replaceAccount(path)

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
      path = path.replace(/\/$/, '')
      keys[path] = key
    },
    get(path) {
      const paths = Object.keys(keys)
      const locked = paths.find(p => path.indexOf(p) == 0)
      return keys[locked]
    },
    remove(path) {
      delete keys[path]
    }
  },

  login({ username, password }) {
    const body = {
      login: username,
      pass: password,
      source: 'web:plugin-vault'
    }

    return request(`${LOGIN_API}/login`, {
      headers: { 'Content-Type': 'application/json' },
      method: 'POST',
      body: JSON.stringify(body)
    })
  },

  refresh() {
    const token = store.state.token
    if (!token) return {}

    return request(`${LOGIN_API}/session`, {
      headers: { Authorization: `Bearer ${token}` }
    })
  },

  async download(path) {
    const options = { headers: {} }
    const key = API.keys.get(path)
    if (key) {
      options.headers['Vault-Key'] = key
    }

    const blob = await fetch('/files' + path, options).then(res => res.blob())

    const a = document.createElement('a')
    const url = window.URL.createObjectURL(blob)
    a.href = url
    a.download = path.substring(path.lastIndexOf('/') + 1)
    document.body.appendChild(a)
    a.click()
    a.remove()
    window.URL.revokeObjectURL(url)
  },

  list(path) {
    const options = { headers: {} }
    const key = API.keys.get(path)
    if (key) {
      options.headers['Vault-Key'] = key
    }

    path = replaceAccount(path)
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
    folder.locked = data.locked
    folder.folders = data.folders
    folder.files = data.files.map(f => {
      const [full, name, ext] = /^(.+?)(?:\.(\w+))?$/.exec(f)
      return { full, name, ext }
    })

    return folder
  },

  upload(path, files) {
    if (!files || !files.length) return
    return sendCommand(path, 'upload', { files, key: API.keys.get(path) })
  },

  delete(path, key) {
    return sendCommand(path, 'delete', { key })
  },

  create(path, key) {
    return sendCommand(path, 'create', { key })
  },

  rename(path, key, name) {
    return sendCommand(path, 'rename', { key, name })
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
