<script>
import API from '@/api'

export default {
  props: {
    path: String
  },

  data: () => ({
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

      try {
        const data = await API.getFolder(this.path)
        this.locked = data.locked
        this.folders = data.folders
        this.files = data.files
      } catch (e) {
        if (e.code === 403) {
          const unlocked = await this.unlockFolder(this.path)
          if (unlocked) {
            this.refresh()
            return
          }
        }

        this.$router.push('/')
      }
    },

    contextmenu(event, item, locked = false) {
      event.stopPropagation()
      this.$root.$emit('contextmenu', {
        event,
        path: this.path + item,
        locked,
        component: this
      })
    },

    isLocked(folder) {
      const path = this.path + folder
      return this.locked.includes(folder) && !API.keys.get(path)
    },

    async unlockFolder(folder) {
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
