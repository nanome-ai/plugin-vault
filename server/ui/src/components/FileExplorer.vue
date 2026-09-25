<template>
  <div class="file-explorer flex flex-col m-4 bg-gray-100 rounded flex-grow">
    <div class="mx-4 mt-4 border-b">
      <toolbar
        @display-mode="displayMode = $event"
        @new-folder="newFolder"
        @show-upload="showDropzone"
        @download-selection="downloadSelection"
      />
      <breadcrumbs :path="path" />
    </div>
    <div
      class="flex-grow relative select-none px-4"
      @click="clearOnBlank"
      @contextmenu.prevent="showContextMenu({ event: $event, path })"
    >
      <file-view-grid v-if="displayMode === 'grid'" :path="path" />
      <file-view-list v-else :path="path" />
      <file-dropzone ref="dropzone" :path="path" />
    </div>

    <div
      v-if="contextmenu.show"
      v-click-out="hideContextMenu"
      @click="hideContextMenu"
      class="contextmenu"
      ref="contextmenu"
      :style="{ top: contextmenu.top, left: contextmenu.left }"
    >
      <ul v-if="multiple">
        <li>
          <button @click="downloadSelection">
            <fa-icon icon="file-archive" transform="shrink-2" class="icon" />
            download {{ contextmenu.selection.length }} items
          </button>
        </li>
        <li v-if="structurePaths.length">
          <button @click="loadInNanome2(false)">
            <fa-icon
              icon="external-link-alt"
              transform="shrink-2"
              class="icon"
            />
            open {{ structurePaths.length | pluralize('file') }} in Nanome 2
          </button>
        </li>
        <li v-if="structurePaths.length">
          <button @click="loadInNanome2(true)">
            <fa-icon icon="plus" transform="shrink-2" class="icon" />
            add {{ structurePaths.length | pluralize('file') }} to a Nanome 2
            workspace…
          </button>
        </li>
        <li v-if="sessionPaths.length">
          <button @click="openSessions">
            <fa-icon
              icon="external-link-alt"
              transform="shrink-2"
              class="icon"
            />
            open {{ sessionPaths.length | pluralize('session') }} in Nanome 2
          </button>
        </li>
      </ul>
      <ul v-else>
        <li v-if="menuOptions.canCreate">
          <button @click="newFolder(contextmenu.path)">
            <fa-icon icon="folder-plus" transform="shrink-2" class="icon" />
            new folder
          </button>
        </li>
        <li v-if="!menuOptions.isFolder">
          <button @click="downloadItem">
            <fa-icon icon="file-download" transform="shrink-2" class="icon" />
            download
          </button>
        </li>
        <li v-else-if="menuOptions.canZip">
          <button @click="downloadFolder(contextmenu.path)">
            <fa-icon icon="file-archive" transform="shrink-2" class="icon" />
            download as zip
          </button>
        </li>
        <li v-if="sessionPaths.length || structurePaths.length">
          <button
            @click="sessionPaths.length ? openSessions() : loadInNanome2(false)"
          >
            <fa-icon
              icon="external-link-alt"
              transform="shrink-2"
              class="icon"
            />
            open in Nanome 2
          </button>
        </li>
        <li v-if="structurePaths.length">
          <button @click="loadInNanome2(true)">
            <fa-icon icon="plus" transform="shrink-2" class="icon" />
            add to a Nanome 2 workspace…
          </button>
        </li>
        <li v-if="menuOptions.canEncrypt">
          <button @click="encryptFolder">
            <fa-icon icon="lock" transform="shrink-2" class="icon" />
            encrypt
          </button>
        </li>
        <li v-else-if="contextmenu.encrypted">
          <button @click="decryptFolder">
            <fa-icon icon="lock-open" transform="shrink-2" class="icon" />
            decrypt
          </button>
        </li>
        <li v-if="menuOptions.canModify && moveDestinations.length">
          <button @click.stop>
            <fa-icon icon="truck-moving" transform="shrink-2" class="icon" />
            move
          </button>
          <ul>
            <li v-for="folder in moveDestinations" :key="folder.value">
              <button @click="moveItem(folder.value)">
                <fa-icon icon="folder" transform="shrink-2" class="icon" />
                {{ folder.label }}
              </button>
            </li>
          </ul>
        </li>
        <li v-if="menuOptions.canModify">
          <button @click="renameItem">
            <fa-icon icon="pen" transform="shrink-2" class="icon" />
            rename
          </button>
        </li>
        <li v-if="menuOptions.canModify">
          <button class="text-red-500" @click="deleteItem">
            <fa-icon icon="trash" transform="shrink-2" class="icon" />
            delete
          </button>
        </li>
      </ul>
    </div>
  </div>
</template>

<script>
import { mapState } from 'vuex'
import API from '@/api'
import { SESSION_FILE, STRUCTURE_FILE } from '@/nanome2'
import Breadcrumbs from '@/components/Breadcrumbs'
import Toolbar from '@/components/Toolbar'
import FileViewGrid from '@/components/FileViewGrid'
import FileViewList from '@/components/FileViewList'
import FileDropzone from '@/components/FileDropzone'

export default {
  components: {
    Breadcrumbs,
    Toolbar,
    FileViewGrid,
    FileViewList,
    FileDropzone
  },

  data: () => ({
    contextmenu: {
      show: false,
      component: null,
      path: '',
      locked: false,
      folders: [],
      encrypted: false,
      key_path: null,
      selection: [],
      top: 0,
      left: 0
    },
    displayMode: 'grid'
  }),

  computed: {
    ...mapState(['nanome2']),

    path() {
      return this.$route.path
    },

    // right-clicked inside a selection of several items
    multiple() {
      return this.contextmenu.selection.length > 1
    },

    // what the right-click acts on
    menuPaths() {
      const { path, selection } = this.contextmenu
      return this.multiple ? selection : [path]
    },

    sessionPaths() {
      if (!this.nanome2) return []
      return this.menuPaths.filter(p => SESSION_FILE.test(p))
    },

    structurePaths() {
      if (!this.nanome2) return []
      return this.menuPaths.filter(p => STRUCTURE_FILE.test(p))
    },

    menuOptions() {
      const { component, path, locked, encrypted, key_path } = this.contextmenu

      const isFolder = path.slice(-1) === '/'
      const inAccount = path.slice(0, 8) === '/account'
      const canCreate = !component || (isFolder && !locked)
      const canModify =
        component && !['/shared/', '/my-org/', '/account/'].includes(path)
      const canEncrypt =
        !encrypted && !key_path && isFolder && canModify && !inAccount

      // zipping the whole shared folder would take in everyone's files
      const canZip = isFolder && !['/', '/shared/'].includes(path)

      return {
        isFolder,
        canCreate,
        canModify,
        canEncrypt,
        canZip
      }
    },

    moveDestinations() {
      const { isFolder } = this.menuOptions
      const { folders, key_path, path } = this.contextmenu

      const split = path.split('/')
      const parts = isFolder ? -2 : -1
      const base = split.slice(0, parts).join('/') + '/'
      const parent = split.slice(0, parts - 1).join('/') + '/'
      const item = split.slice(parts)[0]

      const items = folders
        .filter(f => f.name !== item)
        .map(f => ({
          label: f.name,
          value: base + f.name
        }))

      const isMovingOutsideLock = key_path === base
      if (parent !== '/' && !isMovingOutsideLock) {
        items.unshift({ label: '.. (parent)', value: parent })
      }

      return items
    }
  },

  watch: {
    path() {
      this.$store.commit('CLEAR_SELECTION')
    }
  },

  mounted() {
    const hideContextOnScroll = () => {
      if (this.contextmenu.show) {
        this.hideContextMenu()
      }
    }

    window.addEventListener('scroll', hideContextOnScroll, { passive: true })
    // capture: see Escape before the open context menu closes itself on it
    window.addEventListener('keydown', this.onKeydown, true)
    this.$root.$on('contextmenu', this.showContextMenu)
    this.$root.$on('download', API.download)

    this.$once('hook:beforeDestroy', () => {
      window.removeEventListener('scroll', hideContextOnScroll)
      window.removeEventListener('keydown', this.onKeydown, true)
      this.$root.$off('contextmenu', this.showContextMenu)
      this.$root.$off('download', API.download)
    })
  },

  methods: {
    refresh() {
      if (this.contextmenu.component) {
        this.contextmenu.component.refresh()
      } else {
        this.$root.$emit('refresh')
      }
    },

    showDropzone() {
      this.$refs.dropzone.show()
    },

    async verifyKey(path, action) {
      let key = API.keys.get(path)
      if (key) return key

      key = await this.$modal.prompt({
        title: `${action} Folder`,
        body: 'Please provide the key for this folder:',
        okTitle: 'continue',
        password: true
      })
      if (!key) return

      const { success } = await API.verifyKey(path, key)
      if (!success) {
        this.$modal.alert({
          title: `${action} Cancelled`,
          body: 'The provided key was incorrect'
        })
        return
      }

      API.keys.add(path, key)
      return key
    },

    async newFolder(path) {
      path = path || this.path
      if (path === '/') {
        path = '/shared/'
      }

      if (this.contextmenu.key_path) {
        const key = await this.verifyKey(path, 'Create')
        if (!key) return
      }

      const folder = await this.$modal.prompt({
        title: 'New Folder',
        body: `Creating folder in ${path}<br>Please provide a name:`,
        default: 'new folder'
      })
      if (!folder) return

      const { success } = await API.create(path + folder)
      if (!success) {
        this.$modal.alert({
          title: 'Name Already Exists',
          body: 'Please select a different name'
        })
        return
      }

      if (path !== this.path) {
        this.$router.push(path)
      } else {
        this.refresh()
      }
    },

    async moveItem(folder) {
      const { path } = this.contextmenu
      const { success } = await API.move(path, folder)

      if (!success) {
        this.$modal.alert({
          title: 'Move Failed',
          body: 'Item already exists at destination'
        })
        return
      }

      this.refresh()
    },

    async deleteItem() {
      const { path, key_path } = this.contextmenu
      const { isFolder } = this.menuOptions

      if (key_path) {
        const key = await this.verifyKey(path, 'Delete')
        if (!key) return
      }

      const confirm = await this.$modal.confirm({
        title: `Delete ${isFolder ? 'Folder' : 'File'}`,
        body: `Are you sure you want to delete ${path}?`,
        okClass: 'danger',
        okTitle: 'delete',
        cancelClass: ''
      })
      if (!confirm) return

      await API.delete(path)
      this.refresh()
    },

    downloadItem() {
      API.download(this.contextmenu.path)
    },

    downloadSelection() {
      const { folder, items } = this.$store.state.selection
      if (!items.length) return
      if (items.length > 1) return this.zip(folder, items)

      const path = folder + items[0]
      if (path.slice(-1) === '/') this.downloadFolder(path)
      else API.download(path)
    },

    async downloadFolder(path) {
      // the route stays URL-encoded when a folder's address is opened directly
      let name = path
        .slice(0, -1)
        .split('/')
        .pop()
      try {
        name = decodeURIComponent(name)
      } catch (e) {}
      try {
        let res = await API.zip(path, [], name)
        if (res.code === 403) {
          const key = await this.verifyKey(path, 'Download')
          if (!key) return
          res = await API.zip(path, [], name)
        }
        this.saveZip(res)
      } catch (e) {
        this.saveZip({ error: e })
      }
    },

    async zip(folder, items) {
      try {
        this.saveZip(await API.zip(folder, items))
      } catch (e) {
        this.saveZip({ error: e })
      }
    },

    saveZip(res) {
      if (!res.success) {
        const message = (res.error && res.error.message) || 'Please try again'
        this.$modal.alert({
          title: 'Download Failed',
          body: escapeHtml(message)
        })
        return
      }

      API.downloadZip(res)
      if (res.skipped.length) {
        const names = res.skipped.map(escapeHtml).join('<br>')
        this.$modal.alert({
          title: 'Encrypted Folders Left Out',
          body:
            'Encrypted folders need their own key, so these are not in the zip:' +
            `<br><b>${names}</b><br><br>` +
            'Each can be downloaded on its own from its right-click menu.'
        })
      }
    },

    openSessions() {
      this.$root.$emit('open-in-nanome2', this.sessionPaths)
    },

    loadInNanome2(pick) {
      this.$root.$emit('load-in-nanome2', { paths: this.structurePaths, pick })
    },

    clearOnBlank(event) {
      if (!event.target.closest('[data-select]')) {
        this.$store.commit('CLEAR_SELECTION')
      }
    },

    onKeydown(e) {
      if (this.$modal.showing) return
      const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName)
      if (typing && e.target.type !== 'checkbox') return

      const { folderItems } = this.$store.state
      const selectAll = (e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'a'
      if (selectAll && folderItems.length) {
        e.preventDefault()
        this.$store.commit('SELECT', {
          folder: this.path,
          items: folderItems.slice()
        })
      } else if (e.key === 'Escape' && !this.contextmenu.show) {
        this.$store.commit('CLEAR_SELECTION')
      }
    },

    async renameItem() {
      const { path, key_path } = this.contextmenu
      const { isFolder } = this.menuOptions
      const itemName = /([^/]+)\/?$/.exec(path)[1]

      if (key_path) {
        const key = await this.verifyKey(path, 'Rename')
        if (!key) return
      }

      const name = await this.$modal.prompt({
        title: `Rename ${isFolder ? 'Folder' : 'File'}`,
        body: `Renaming ${path}<br>Please provide a name:`,
        default: itemName
      })
      if (!name) return

      await API.rename(path, name)
      this.refresh()
    },

    async encryptFolder() {
      const { path } = this.contextmenu

      const key = await this.$modal.prompt({
        title: 'Lock Folder',
        body: `Encrypting ${path}<br>Please provide a key:`,
        okTitle: 'continue',
        password: true
      })
      if (!key) return

      const verifyKey = await this.$modal.prompt({
        title: 'Lock Folder',
        body: `Encrypting ${path}<br>Please verify your key:`,
        okTitle: 'continue',
        password: true
      })
      if (!verifyKey) return

      if (key !== verifyKey) {
        this.$modal.alert({
          title: 'Encryption Cancelled',
          body: 'The keys you provided did not match'
        })
        return
      }

      const yes = await this.$modal.confirm({
        title: 'Confirm Encryption',
        body:
          'Are you sure you want to continue?<br><br><b>NOTE:</b> ' +
          'If you lose your key, you will be unable to recover the files in this folder.',
        okTitle: 'encrypt',
        okClass: 'danger'
      })
      if (!yes) return

      await API.encrypt(path, key)
      API.keys.add(path, key)
      this.refresh()
    },

    async decryptFolder() {
      const { path } = this.contextmenu

      const key = await this.$modal.prompt({
        title: 'Decrypt Folder',
        body: `Decrypting ${path}<br>Please enter the key:`,
        password: true
      })
      if (!key) return

      await API.decrypt(path, key)
      API.keys.remove(path)
      this.refresh()
    },

    async showContextMenu(e) {
      // right-clicking empty space leaves the selection behind
      if (!e.component) this.$store.commit('CLEAR_SELECTION')

      this.contextmenu.show = true
      this.contextmenu.path = e.path
      this.contextmenu.locked = e.locked
      this.contextmenu.folders = e.folders
      this.contextmenu.encrypted = e.encrypted
      this.contextmenu.key_path = e.key_path
      this.contextmenu.selection = e.selection || []
      this.contextmenu.component = e.component

      await this.$nextTick()
      const el = this.$refs.contextmenu
      const { pageX, pageY } = e.event
      const maxHeight = innerHeight + document.scrollingElement.scrollTop
      const top = Math.min(pageY + 3, maxHeight - el.clientHeight - 10)
      const left = Math.min(pageX + 3, innerWidth - el.clientWidth - 10)
      this.contextmenu.top = top + 'px'
      this.contextmenu.left = left + 'px'
    },

    hideContextMenu() {
      this.contextmenu.show = false
      this.contextmenu.path = ''
      this.contextmenu.locked = false
      this.contextmenu.folders = []
      this.contextmenu.encrypted = false
      this.contextmenu.key_path = null
      this.contextmenu.selection = []
      this.contextmenu.component = null
    }
  }
}

const escapeHtml = text =>
  String(text).replace(
    /[&<>"']/g,
    c =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[
        c
      ])
  )
</script>

<style lang="scss">
.file-explorer {
  .contextmenu {
    @apply absolute text-gray-800 text-xl;

    ul {
      @apply bg-white rounded shadow-md whitespace-no-wrap;
      min-width: 12rem;
    }

    li {
      @apply relative;

      > ul {
        @apply hidden absolute top-0;
        left: 100%;
      }

      &:hover > button {
        @apply bg-gray-200;
      }

      &:hover > ul {
        @apply block;
      }
    }

    button {
      @apply px-2 py-1 w-full text-left rounded;

      &:focus {
        @apply bg-gray-200 outline-none;

        + ul {
          @apply block;
        }
      }

      .icon {
        @apply mx-1 w-8;
      }
    }
  }
}
</style>
