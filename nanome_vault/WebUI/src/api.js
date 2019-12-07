import store from '@/store'
const LOGIN_API = 'https://api.nanome.ai/user'

function replaceAccount(path) {
  return path.replace(/^\/account/, '/' + store.state.unique)
}

function request(url, options) {
  return fetch(url, options).then(res => res.json())
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
    } else {
      data.append(key, params[key])
    }
  }

  return request('/files' + path, {
    method: 'POST',
    body: data
  })
}

const API = {
  login({ username, password }) {
    const body = {
      login: username,
      pass: password,
      source: 'web:plugin-vault'
    }

    return request(`${LOGIN_API}/login`, {
      headers: {
        'Content-Type': 'application/json'
      },
      method: 'POST',
      body: JSON.stringify(body)
    })
  },

  refresh() {
    const token = store.state.token
    if (!token) return {}

    return request(`${LOGIN_API}/session`, {
      headers: {
        Authorization: `Bearer ${token}`
      },
      method: 'GET'
    })
  },

  list(path) {
    path = replaceAccount(path)
    return request('/files' + path)
  },

  async getFolder(path) {
    const folder = {
      path: '',
      parent: '',
      files: [],
      folders: []
    }

    if (path.slice(-1) !== '/') {
      path += '/'
    }

    if (path !== '/') {
      const lastSlash = path.slice(0, -1).lastIndexOf('/')
      folder.parent = path.substring(0, lastSlash) + '/'
    }

    const data = await API.list(path)
    if (!data.success) throw new Error(data.error)
    folder.path = path

    folder.folders = data.folders
    folder.files = data.files.map(f => {
      const [full, name, ext] = /^(.+?)(?:\.(\w+))?$/.exec(f)
      return { full, name, ext }
    })

    return folder
  },

  upload(path, files) {
    if (!files || !files.length) return
    return sendCommand(path, 'upload', { files })
  },

  delete(path) {
    return sendCommand(path, 'delete')
  },

  create(path) {
    return sendCommand(path, 'create')
  },

  encrypt(path, key) {
    return sendCommand(path, 'encrypt', { key })
  },

  decrypt(path, key) {
    return sendCommand(path, 'decrypt', { key })
  }
}

export default API
