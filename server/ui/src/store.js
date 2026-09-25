import Vue from 'vue'
import Vuex from 'vuex'
import API from '@/api'
import router from '@/router'

Vue.use(Vuex)

const state = {
  authEnabled: false,
  token: localStorage.getItem('user-token') || null,
  unique: null,
  name: null,
  org: null,
  extensions: {
    supported: [],
    extras: [],
    converted: [],
    external: []
  },
  message: null,
  // { url, toolId } of the Nanome 2 web app, or null when turned off
  nanome2: null,
  // selected items (names in folder, folders end in '/'), one folder at a time
  selection: { folder: null, items: [], anchor: null },
  // names of the items in the folder being viewed, for select all
  folderItems: []
}

const getters = {
  allExtensions: ({ extensions }) => [].concat(...Object.values(extensions))
}

const mutations = {
  AUTH_ENABLED(state) {
    state.authEnabled = true
  },

  PATCH_USER(state, payload) {
    Object.assign(state, payload)
  },

  SET_EXTENSIONS(state, extensions) {
    state.extensions = extensions
  },

  SET_MESSAGE(state, message) {
    state.message = message
  },

  SET_NANOME2(state, nanome2) {
    state.nanome2 = nanome2 || null
  },

  SELECT(state, { folder, items, anchor = null }) {
    state.selection = { folder, items, anchor }
  },

  CLEAR_SELECTION(state) {
    state.selection = { folder: null, items: [], anchor: null }
  },

  SET_FOLDER_ITEMS(state, items) {
    state.folderItems = items
  }
}

async function saveSession(commit, { success, results }) {
  if (success) {
    const user = {
      unique: results.user.unique,
      name: results.user.name,
      token: results.token.value,
      org: results.organization && `org-${results.organization.id}`
    }
    commit('PATCH_USER', user)
    localStorage.setItem('user-token', results.token.value)

    await API.create('/' + user.unique).catch(e => {})

    if (user.org) {
      await API.create('/' + user.org).catch(e => {})
    }

    return true
  } else {
    localStorage.removeItem('user-token')
    commit('PATCH_USER', { token: null })
    return false
  }
}

const actions = {
  async getInfo({ commit }) {
    const { extensions, message, nanome2 } = await API.getInfo()
    commit('SET_EXTENSIONS', extensions)
    commit('SET_MESSAGE', message)
    commit('SET_NANOME2', nanome2)
  },

  async login({ commit }, creds) {
    const data = await API.login(creds)
    if (data.code !== 200) {
      throw new Error(data.error.message)
    }
    return saveSession(commit, data)
  },

  async loginSSO(_, email) {
    const data = await API.loginSSO(email, window.location.href)
    if (data.code !== 200) {
      throw new Error(data.error.message)
    }
    return data.results
  },

  async refresh({ commit }) {
    const data = await API.refresh()
    return saveSession(commit, data)
  },

  async logout({ commit }) {
    commit('PATCH_USER', {
      token: null,
      name: null,
      unique: null,
      org: null
    })
    localStorage.removeItem('user-token')
    router.push('/')
  }
}

export default new Vuex.Store({
  state,
  getters,
  mutations,
  actions
})
