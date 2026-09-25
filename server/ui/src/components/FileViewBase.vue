<script>
import API from '@/api'
import debounce from '@/helpers/debounce'
import { nextSelection } from '@/helpers/selection'
import SelectBox from '@/components/SelectBox'

export default {
  components: { SelectBox },

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

  computed: {
    // the root holds only shared, my org and account
    selectable() {
      return this.path !== '/'
    },

    order() {
      const folders = this.folders.map(f => f.name + '/')
      return folders.concat(this.files.map(f => f.full))
    },

    selected() {
      const { folder, items } = this.$store.state.selection
      return folder === this.path ? items : []
    }
  },

  watch: {
    path: {
      handler: 'refresh',
      immediate: true
    },
    '$store.state.token': 'refresh'
  },

  mounted() {
    const debounceRefresh = debounce(this.refresh, 500)
    this.$root.$on('refresh', debounceRefresh)
    this.$once('hook:beforeDestroy', () => {
      this.$root.$off('refresh', debounceRefresh)
    })
  },

  methods: {
    async refresh(newPath) {
      if (this.beforeRefresh && newPath) this.beforeRefresh()
      this.loading = true
      if (!this.nested) this.$store.commit('SET_FOLDER_ITEMS', [])

      const needsAuth = /^\/(account|my-org)\//.test(this.path)
      if (needsAuth && !this.$store.state.unique) {
        await this.$modal.login()
      }

      try {
        const data = await API.getFolder(this.path)
        this.key_path = data.locked_path
        this.encrypted = data.locked
        this.folders = data.folders
        this.files = data.files
        this.loading = false
        this.syncSelection()
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

      // like a file manager: right-clicking outside the selection selects the
      // item, right-clicking inside it acts on all of it
      const selectable = this.selectable && this.order.includes(item)
      if (selectable && !this.isSelected(item)) {
        this.setSelection({ items: [item], anchor: item })
      }

      this.$root.$emit('contextmenu', {
        event,
        path: this.path + item,
        locked: this.isLocked(item),
        folders: this.folders.filter(f => !this.encrypted.includes(f.name)),
        encrypted,
        key_path: this.key_path,
        selection: selectable ? this.selected.map(i => this.path + i) : [],
        component: this
      })
    },

    isSelected(item) {
      return this.selected.includes(item)
    },

    setSelection({ items, anchor }) {
      this.$store.commit('SELECT', { folder: this.path, items, anchor })
    },

    select(event, item) {
      if (!this.selectable) return

      const toggle = event.metaKey || event.ctrlKey
      const range = event.shiftKey
      // stop cmd/shift-click on a folder link opening a tab or window
      if (toggle || range) event.preventDefault()

      const { folder, items, anchor } = this.$store.state.selection
      const current = folder === this.path ? { items, anchor } : {}
      const next = nextSelection(
        { items: [], anchor: null, ...current },
        this.order,
        item,
        { toggle, range }
      )
      this.setSelection(next)
    },

    toggleSelect(item) {
      this.select({ metaKey: true, preventDefault() {} }, item)
    },

    // after a refresh: offer the items for select all, forget removed ones
    syncSelection() {
      if (!this.nested) {
        const items = this.selectable ? this.order : []
        this.$store.commit('SET_FOLDER_ITEMS', items)
      }

      const { anchor } = this.$store.state.selection
      const kept = this.selected.filter(i => this.order.includes(i))
      if (kept.length !== this.selected.length) {
        this.setSelection({ items: kept, anchor })
      }
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
