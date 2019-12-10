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
      v-show="contextmenu.show"
      v-click-out="hideContextMenu"
      @click="hideContextMenu"
      class="contextmenu"
      :style="{ top: contextmenu.top, left: contextmenu.left }"
    >
      <ul>
        <li v-if="menuOptions.isFolder">
          <button class="text-gray-800" @click="newFolder(contextmenu.path)">
            <fa-icon icon="folder-plus" />
            new folder
          </button>
        </li>
        <li v-else>
          <button class="text-gray-800" @click="download(contextmenu.path)">
            <fa-icon icon="file-download" />
            download
          </button>
        </li>
        <li v-if="menuOptions.encryptable">
          <button class="text-gray-800" @click="encrypt(contextmenu.path)">
            <fa-icon icon="lock" />
            encrypt
          </button>
        </li>
        <li v-else-if="contextmenu.locked">
          <button class="text-gray-800" @click="decrypt(contextmenu.path)">
            <fa-icon icon="lock-open" />
            decrypt
          </button>
        </li>
        <li v-if="menuOptions.deletable">
          <button class="text-red-500" @click="deleteItem">
            <fa-icon icon="trash" />
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
      const { component, path, locked } = this.contextmenu

      const isFolder = path.slice(-1) === '/'
      const deletable = component && !['/shared/', '/account/'].includes(path)
      const encryptable =
        !locked && isFolder && !['/', '/shared/'].includes(path)

      return {
        isFolder,
        deletable,
        encryptable
      }
    }
  },

  mounted() {
    this.$root.$on('contextmenu', this.showContextMenu)
    this.$root.$on('download', this.download)
  },

  destroyed() {
    this.$root.$off('contextmenu', this.showContextMenu)
    this.$root.$off('download', this.download)
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

    async newFolder(path) {
      path = path || this.path
      if (path === '/') {
        path = '/shared/'
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
      const { path, locked } = this.contextmenu

      const confirm = await this.$modal.confirm({
        title: 'Delete Item',
        body: `Are you sure you want to delete ${path}?`,
        okClass: 'danger',
        okTitle: 'delete',
        cancelClass: ''
      })
      if (!confirm) return

      let key
      if (locked) {
        key = await this.$modal.prompt({
          title: 'Delete Folder',
          body: 'Please provide the key for this folder:',
          okTitle: 'delete',
          okTitle: 'delete',
          cancelClass: '',
          password: true
        })
        if (!key) return

        const { success } = await API.verifyKey(path, key)
        if (!success) {
          this.$modal.alert({
            title: 'Delete Cancelled',
            body: 'The provided key was incorrect'
          })
          return
        }
      }

      await API.delete(path, key)
      this.refresh()
    },

    download(path) {
      API.download(path)
    },

    async encrypt(path) {
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
        okTitle: 'yes'
      })
      if (!yes) return

      await API.encrypt(path, key)
      API.keys.add(path, key)
      this.refresh()
    },

    async decrypt(path) {
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

    showContextMenu({ event, path, locked, component }) {
      this.contextmenu.show = true
      this.contextmenu.path = path
      this.contextmenu.locked = locked
      this.contextmenu.component = component
      this.contextmenu.top = event.pageY + 1 + 'px'
      this.contextmenu.left = event.pageX + 1 + 'px'
    },

    hideContextMenu() {
      this.contextmenu.show = false
      this.contextmenu.path = ''
      this.contextmenu.locked = false
      this.contextmenu.component = null
    }
  }
}
</script>

<style lang="scss">
.file-explorer {
  .contextmenu {
    @apply absolute bg-white text-xl w-40 rounded shadow-md overflow-hidden;

    button {
      @apply px-4 py-1 w-full text-left;

      &:hover {
        @apply bg-gray-200;
      }
      &:focus {
        @apply outline-none;
      }
    }
  }
}
</style>
