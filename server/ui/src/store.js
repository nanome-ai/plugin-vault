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
    converted: []
  },
  message: null
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
    const { extensions, message } = await API.getInfo()
    commit('SET_EXTENSIONS', extensions)
    commit('SET_MESSAGE', message)
  },

  async login({ commit }, creds) {
    const data = await API.login(creds)
    return saveSession(commit, data)
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
