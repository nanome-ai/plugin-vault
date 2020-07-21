<template>
  <div class="file-explorer flex flex-col m-4 bg-gray-100 rounded flex-grow">
    <div class="mx-4 mt-4 border-b">
      <toolbar
        @display-mode="displayMode = $event"
        @new-folder="newFolder"
        @show-upload="showDropzone"
      />
      <breadcrumbs :path="path" />
    </div>
    <div
      class="flex-grow relative select-none px-4"
      @contextmenu.prevent="showContextMenu({ event: $event, path })"
    >
      <file-view-grid v-if="displayMode === 'grid'" :path="path" />
      <file-view-list v-else :path="path" />
      <file-dropzone ref="dropzone" @upload="refresh" :path="path" />
    </div>

    <div
      v-if="contextmenu.show"
      v-click-out="hideContextMenu"
      @click="hideContextMenu"
      class="contextmenu"
      ref="contextmenu"
      :style="{ top: contextmenu.top, left: contextmenu.left }"
    >
      <ul>
        <li v-if="menuOptions.canCreate">
          <button class="text-gray-800" @click="newFolder(contextmenu.path)">
            <fa-icon icon="folder-plus" transform="shrink-2" class="icon" />
            new folder
          </button>
        </li>
        <li v-if="!menuOptions.isFolder">
          <button class="text-gray-800" @click="downloadItem">
            <fa-icon icon="file-download" transform="shrink-2" class="icon" />
            download
          </button>
        </li>
        <li v-if="menuOptions.canEncrypt">
          <button class="text-gray-800" @click="encryptFolder">
            <fa-icon icon="lock" transform="shrink-2" class="icon" />
            encrypt
          </button>
        </li>
        <li v-else-if="contextmenu.encrypted">
          <button class="text-gray-800" @click="decryptFolder">
            <fa-icon icon="lock-open" transform="shrink-2" class="icon" />
            decrypt
          </button>
        </li>
        <li v-if="menuOptions.canModify">
          <button class="text-gray-800" @click="renameItem">
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
import API from '@/api'
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
      encrypted: false,
      key_path: null,
      top: 0,
      left: 0
    },
    displayMode: 'grid'
  }),

  computed: {
    path() {
      return this.$route.path
    },

    menuOptions() {
      const { component, path, locked, encrypted, key_path } = this.contextmenu

      const isFolder = path.slice(-1) === '/'
      const canCreate = !component || (isFolder && !locked)
      const canModify = component && !['/shared/', '/account/'].includes(path)
      const canEncrypt = !encrypted && !key_path && isFolder && canModify

      return {
        isFolder,
        canCreate,
        canModify,
        canEncrypt
      }
    }
  },

  mounted() {
    this.$root.$on('contextmenu', this.showContextMenu)
    this.$root.$on('download', API.download)

    this.$once('hook:beforeDestroy', () => {
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
      this.contextmenu.show = true
      this.contextmenu.path = e.path
      this.contextmenu.locked = e.locked
      this.contextmenu.encrypted = e.encrypted
      this.contextmenu.key_path = e.key_path
      this.contextmenu.component = e.component

      await this.$nextTick()
      const el = this.$refs.contextmenu
      const { pageX, pageY } = e.event
      const top = Math.min(pageY + 3, innerHeight - el.clientHeight - 10)
      const left = Math.min(pageX + 3, innerWidth - el.clientWidth - 10)
      this.contextmenu.top = top + 'px'
      this.contextmenu.left = left + 'px'
    },

    hideContextMenu() {
      this.contextmenu.show = false
      this.contextmenu.path = ''
      this.contextmenu.locked = false
      this.contextmenu.encrypted = false
      this.contextmenu.key_path = null
      this.contextmenu.component = null
    }
  }
}
</script>

<style lang="scss">
.file-explorer {
  .contextmenu {
    @apply absolute bg-white text-xl w-48 rounded shadow-md overflow-hidden;

    button {
      @apply px-2 py-1 w-full text-left;

      &:hover {
        @apply bg-gray-200;
      }
      &:focus {
        @apply outline-none;
      }

      .icon {
        @apply mx-1 w-8;
      }
    }
  }
}
</style>
