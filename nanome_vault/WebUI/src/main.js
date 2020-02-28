import '@/assets/css/tailwind.css'
import './fa.config.js'

import Vue from 'vue'
import App from './App.vue'
import router from './router'
import store from './store'
import Modal from '@/components/Modal'

Vue.config.productionTip = false

Vue.directive('click-out', {
  bind(el, binding, vnode) {
    el.data = {
      stop: e => e.stopPropagation(),
      event: () => vnode.context[binding.expression](),
      esc: e => e.key === 'Escape' && el.data.event()
    }

    setTimeout(() => {
      document.body.addEventListener('click', el.data.event)
      document.body.addEventListener('keydown', el.data.esc)
      el.addEventListener('click', el.data.stop)
    }, 0)
  },
  unbind(el) {
    document.body.removeEventListener('click', el.data.event)
    document.body.removeEventListener('keydown', el.data.esc)
    el.removeEventListener('click', el.data.stop)
  }
})

Vue.filter('extensions', extensions => {
  if (!extensions) return ''
  return extensions.map(ext => '.' + ext).join(', ')
})

store.dispatch('getInfo')
store.dispatch('refresh')

const app = new Vue({
  router,
  store,
  render: h => h(App)
}).$mount('#app')

// global modal singleton
const VModal = Vue.extend(Modal)
const modal = new VModal({ store })
modal.$mount()
Vue.prototype.$modal = modal
app.$root.$el.appendChild(modal.$el)
