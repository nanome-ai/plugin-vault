<template>
  <div v-if="showing" @click.self="cancel" class="modal">
    <div class="modal-body">
      <div class="p-4">
        <h2 v-if="options.title">{{ options.title }}</h2>
        <p v-if="options.body" v-html="options.body"></p>

        <div class="mt-2">
          <template v-if="options.type === 'prompt'">
            <input
              ref="prompt"
              v-model="input1"
              :type="options.password ? 'password' : 'text'"
            />
          </template>

          <template v-else-if="options.type === 'login'">
            <input
              ref="login"
              v-model="input1"
              :class="{ 'border-red-500': error }"
              placeholder="username"
              type="text"
            />
            <input
              v-model="input2"
              :class="{ 'border-red-500': error }"
              placeholder="password"
              type="password"
            />

            <p v-if="error" class="text-red-500">{{ error }}</p>

            <p>
              <a
                key="login-forgot"
                href="https://home.nanome.ai/login/forgot"
                target="_blank"
                class="link text-blue-500"
                >forgot password?</a
              >
              or

              <a
                key="login-sso"
                class="link text-blue-500"
                @click.stop="options.type = 'login-sso'"
                >log in with SSO</a
              >
            </p>

            <p></p>

            <p class="text-xs text-gray-700">
              Don't have a Nanome account?
              <a
                href="https://home.nanome.ai/register"
                target="_blank"
                class="link text-blue-500"
              >
                Register here
              </a>
            </p>
          </template>

          <template v-else-if="options.type === 'login-sso'">
            <input
              ref="login"
              v-model="input1"
              :class="{ 'border-red-500': error }"
              placeholder="email"
              type="text"
            />

            <p v-if="error" class="text-red-500">
              {{ error }}
            </p>

            <p>
              <a
                key="login-username"
                class="link text-blue-500"
                @click.stop="options.type = 'login'"
              >
                log in with username
              </a>
            </p>

            <p class="text-xs text-gray-700">
              Don't have a Nanome account?
              <a
                href="https://home.nanome.ai/register"
                target="_blank"
                class="link text-blue-500"
              >
                Register here
              </a>
            </p>
          </template>
        </div>
      </div>

      <div class="modal-actions">
        <button
          v-if="options.type !== 'alert'"
          @click="cancel"
          class="btn"
          :class="options.cancelClass"
        >
          {{ options.cancelTitle }}
        </button>
        <button
          @click="ok"
          class="btn"
          :class="options.okClass"
          :disabled="okDisabled"
        >
          {{ options.okTitle }}
        </button>
      </div>
    </div>
  </div>
</template>

<script>
const defaults = {
  type: 'confirm',
  title: '',
  body: '',
  default: '',
  okTitle: 'ok',
  okClass: 'primary',
  cancelTitle: 'cancel',
  cancelClass: '',
  password: false
}

const deferred = () => {
  let res, rej

  const promise = new Promise((resolve, reject) => {
    res = resolve
    rej = reject
  })

  promise.resolve = res
  promise.reject = rej

  return promise
}

export default {
  data: () => ({
    showing: false,
    error: null,
    loading: false,
    options: { ...defaults },
    input1: '',
    input2: '',
    deferred: deferred()
  }),

  computed: {
    okDisabled() {
      if (this.loading) return true

      if (this.options.type === 'login') {
        return !this.input1 || !this.input2
      } else if (['login-sso', 'prompt'].includes(this.options.type)) {
        return !this.input1
      }

      return false
    }
  },

  watch: {
    'options.type'() {
      this.error = null
      this.input1 = ''
      this.input2 = ''
    }
  },

  mounted() {
    document.body.addEventListener('keydown', this.onKeydown)
  },

  destroyed() {
    document.body.removeEventListener('keydown', this.onKeydown)
  },

  methods: {
    onKeydown(e) {
      if (!this.showing) return

      if (e.key === 'Enter') {
        this.ok()
      } else if (e.key === 'Escape') {
        this.cancel()
      }
    },

    show(options) {
      Object.assign(this.options, defaults, options)
      this.showing = true

      if (this.options.type === 'prompt') {
        this.input1 = this.options.default
        this.$nextTick(() => {
          const input = this.$refs.prompt
          input.focus()
          input.setSelectionRange(0, input.value.lastIndexOf('.'))
        })
      } else if (this.options.type === 'login') {
        this.$nextTick(() => this.$refs.login.focus())
      }

      this.deferred = deferred()
      return this.deferred
    },

    alert(options) {
      return this.show({
        type: 'alert',
        okClass: '',
        ...options
      })
    },

    confirm(options) {
      return this.show({
        type: 'confirm',
        ...options
      })
    },

    prompt(options) {
      return this.show({
        type: 'prompt',
        ...options
      })
    },

    login(options) {
      return this.show({
        type: 'login',
        title: 'Log in to Nanome',
        body: 'Log in using your Nanome account',
        okTitle: 'log in',
        okClass: 'primary',
        cancelClass: '',
        ...options
      })
    },

    reset() {
      this.showing = false
      this.input1 = ''
      this.input2 = ''
      this.deferred = null
    },

    cancel() {
      if (this.options.type === 'confirm') {
        this.deferred.resolve(false)
      } else {
        this.deferred.resolve(undefined)
      }

      this.reset()
    },

    ok() {
      if (this.okDisabled) return

      let data
      if (this.options.type === 'confirm') {
        data = true
      } else if (this.options.type === 'prompt') {
        data = this.input1
      } else if (this.options.type === 'login') {
        this.attemptLogin()
        return
      } else if (this.options.type === 'login-sso') {
        this.attemptLoginSSO()
        return
      }

      this.deferred.resolve(data)
      this.reset()
    },

    async attemptLogin() {
      const deferred = this.deferred
      this.error = null

      const creds = {
        username: this.input1,
        password: this.input2
      }

      let success
      while (true) {
        try {
          this.loading = true
          success = await this.$store.dispatch('login', creds)
          break
        } catch (e) {
          this.loading = false
          this.error = e.message
          if (!this.error.includes('2FA')) break

          creds.tfa_code = await this.prompt({
            title: 'Enter 2FA code',
            body: 'Or use a one time recovery code',
            okTitle: 'submit'
          })
          if (!creds.tfa_code) {
            deferred.resolve(false)
            this.reset()
            return
          }
        }
      }
      this.loading = false

      if (success) {
        deferred.resolve(true)
        this.reset()
      }
    },

    async attemptLoginSSO() {
      this.error = null
      this.loading = true

      try {
        const url = await this.$store.dispatch('loginSSO', this.input1)
        window.open(url, '_self')
      } catch (e) {
        this.loading = false
        this.error = e.message
      }
    }
  }
}
</script>

<style lang="scss">
.modal {
  @apply fixed inset-0 z-50 flex items-center justify-center;
  background: rgba(0, 0, 0, 0.5);

  &-body {
    @apply bg-white rounded shadow overflow-hidden;
    width: 20rem;
  }

  &-actions {
    @apply w-full flex justify-between;

    button {
      @apply w-full;
    }
  }
}
</style>
