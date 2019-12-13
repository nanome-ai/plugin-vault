<script>
import API from '@/api'

export default {
  props: {
    path: String
  },

  data: () => ({
    loading: true,
    locked: [],
    folders: [],
    files: []
  }),

  watch: {
    path: {
      handler: 'refresh',
      immediate: true
    }
  },

  mounted() {
    this.$root.$on('refresh', this.refresh)
  },

  destroyed() {
    this.$root.$off('refresh', this.refresh)
  },

  methods: {
    async refresh(newPath) {
      if (this.beforeRefresh && newPath) this.beforeRefresh()
      this.loading = true

      try {
        const data = await API.getFolder(this.path)
        this.locked = data.locked
        this.folders = data.folders
        this.files = data.files
        this.loading = false
      } catch (e) {
        if (e.code === 403) {
          const unlocked = await this.unlockFolder()
          if (unlocked) {
            this.refresh()
            return
          }
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
        component: this
      })
    },

    isLocked(folder) {
      folder = folder.replace(/\/$/, '')
      const path = this.path + folder
      const noKey = !API.keys.get(path)
      const isLocked = this.loading || this.locked.includes(folder)
      return noKey && isLocked
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
