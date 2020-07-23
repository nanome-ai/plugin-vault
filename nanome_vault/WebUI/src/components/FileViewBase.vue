<script>
import API from '@/api'

export default {
  props: {
    path: String
  },

  data: () => ({
    loading: true,
    key_path: null,
    encrypted: [],
    folders: [],
    files: []
  }),

  watch: {
    path: {
      handler: 'refresh',
      immediate: true
    },
    '$store.state.token': 'refresh'
  },

  mounted() {
    this.$root.$on('refresh', this.refresh)
    this.$once('hook:beforeDestroy', () => {
      this.$root.$off('refresh', this.refresh)
    })
  },

  methods: {
    async refresh(newPath) {
      if (this.beforeRefresh && newPath) this.beforeRefresh()
      this.loading = true

      try {
        const data = await API.getFolder(this.path)
        this.key_path = data.locked_path
        this.encrypted = data.locked
        this.folders = data.folders
        this.files = data.files
        this.loading = false
      } catch (e) {
        if (e.code === 401) {
          this.$store.commit('AUTH_ENABLED')
          return
        }

        if (e.code === 403) {
          const unlocked = await this.unlockFolder()
          if (unlocked) return this.refresh()
        }

        this.$router.push('/')
      }
    },

    contextmenu(event, item, encrypted = false) {
      event.stopPropagation()
      this.$root.$emit('contextmenu', {
        event,
        path: this.path + item,
        locked: this.isLocked(item),
        encrypted,
        key_path: this.key_path,
        component: this
      })
    },

    isLocked(folder) {
      folder = folder.replace(/\/$/, '')
      const isEncrypted = this.loading || this.encrypted.includes(folder)
      const noKey = !API.keys.get(this.path + folder)
      return isEncrypted && noKey
    },

    async unlockFolder(folder = '') {
      const path = this.path + folder
      if (!this.isLocked(folder)) {
        return true
      }

      const key = await this.$modal.prompt({
        title: 'Unlock Folder',
        body: `Attempting to view ${path}<br>Please enter key:`,
        password: true
      })
      if (!key) return false

      const { success } = await API.verifyKey(path, key)
      if (!success) {
        await this.$modal.alert({
          title: 'Unlock Failed',
          body: 'The provided key was incorrect'
        })
        return false
      }

      API.keys.add(path, key)
      return true
    },

    async openLocked(folder) {
      const unlocked = await this.unlockFolder(folder)
      if (unlocked) {
        this.$router.push(this.path + folder).catch(e => {})
      }
    }
  }
}
</script>
