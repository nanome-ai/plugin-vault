<template>
  <div v-if="!loading" class="file-view-list text-lg">
    <ul v-if="files.length || folders.length" class="w-full">
      <template v-for="folder in folders">
        <li :key="folder.name" class="p-2 flex items-center">
          <fa-icon
            icon="angle-right"
            class="text-2xl w-8 cursor-pointer text-gray-500 hover:text-black"
            fixed-width
            @click="toggleFolder(folder.name, isLocked(folder.name))"
            :class="{ expanded: expanded[folder.name] }"
          />
          <a
            v-if="encrypted.includes(folder.name)"
            :title="`${folder.name} (${folder.size_text})`"
            class="file cursor-default"
            @dblclick="openLocked(folder.name)"
            @contextmenu.prevent="contextmenu($event, folder.name + '/', true)"
          >
            <fa-layers class="icon mr-2">
              <fa-icon icon="folder" />
              <fa-icon
                :icon="isLocked(folder.name) ? 'lock' : 'lock-open'"
                class="text-white"
                transform="down-1 shrink-11"
              />
            </fa-layers>
            <div class="truncate">{{ folder.name }}</div>
          </a>
          <router-link
            v-else
            :title="`${folder.name} (${folder.size_text})`"
            :to="`${path}${folder.name}/`"
            class="file cursor-default"
            event="dblclick"
            @contextmenu.native.prevent="contextmenu($event, folder.name + '/')"
          >
            <fa-icon icon="folder" class="icon mr-2" />
            <div class="truncate">{{ folder.name }}</div>
          </router-link>
        </li>

        <li
          v-if="expanded[folder.name]"
          :key="folder.name + '-expanded'"
          class="pl-8"
        >
          <file-view-list :path="`${path}${folder.name}/`" nested />
        </li>
      </template>

      <template v-if="path == '/'">
        <li v-if="org" class="p-2 flex items-center">
          <fa-icon
            icon="angle-right"
            class="text-2xl w-8 cursor-pointer text-gray-500 hover:text-black"
            fixed-width
            @click="toggleFolder('my-org')"
            :class="{ expanded: expanded['my-org'] }"
          />

          <router-link
            to="/my-org/"
            @contextmenu.native.prevent="contextmenu($event, 'my-org/')"
            event="dblclick"
            class="file cursor-default"
          >
            <fa-layers class="icon mr-2">
              <fa-icon icon="folder" />
              <fa-icon
                icon="sitemap"
                class="text-white"
                transform="down-1 left-2 shrink-11"
              />
            </fa-layers>
            <div>my org</div>
          </router-link>
        </li>

        <li v-if="expanded['account']" key="account-expanded" class="pl-8">
          <file-view-list v-if="unique" :path="`${path}account/`" nested />
        </li>

        <li class="p-2 flex items-center">
          <fa-icon
            icon="angle-right"
            class="text-2xl w-8 cursor-pointer text-gray-500 hover:text-black"
            fixed-width
            @click="!unique ? $modal.login() : toggleFolder('account')"
            :class="{ expanded: expanded['account'] }"
          />

          <a v-if="!unique" @click="$modal.login()" class="file">
            <fa-layers class="icon mr-2">
              <fa-icon icon="folder" />
              <fa-icon
                icon="lock"
                class="text-white"
                transform="down-1 shrink-11"
              />
            </fa-layers>
            <div>account</div>
          </a>

          <router-link
            v-else
            to="/account/"
            @contextmenu.native.prevent="contextmenu($event, 'account/')"
            event="dblclick"
            class="file cursor-default"
          >
            <fa-layers class="icon mr-2">
              <fa-icon icon="folder" />
              <fa-icon
                icon="lock-open"
                class="text-white"
                transform="down-1 shrink-11"
              />
            </fa-layers>
            <div>account</div>
          </router-link>
        </li>

        <li v-if="expanded['account']" key="account-expanded" class="pl-8">
          <file-view-list v-if="unique" :path="`${path}account/`" nested />
        </li>
      </template>

      <li
        v-for="file in files"
        :key="file.full"
        :title="`${file.full} (${file.size_text})`"
        class="p-2 file"
        @contextmenu.prevent="contextmenu($event, file.full)"
        @dblclick="$root.$emit('download', path + file.full)"
      >
        <div class="w-8"></div>
        <fa-layers class="icon mr-2">
          <fa-icon icon="file" />
          <fa-text
            class="text-white"
            :transform="'down-4 shrink-' + (file.ext.length < 5 ? 12 : 13)"
            :value="file.ext"
          />
        </fa-layers>
        <div class="truncate">{{ file.full }}</div>
      </li>
    </ul>

    <div v-else-if="!nested" class="text-xl pt-8 pb-4">
      <fa-layers class="text-6xl">
        <fa-icon icon="folder" />
        <fa-icon
          icon="sad-tear"
          class="text-white"
          transform="down-1 shrink-10"
        />
      </fa-layers>
      <br />
      this folder is empty
    </div>
  </div>
</template>

<script>
import { mapState } from 'vuex'
import FileViewBase from '@/components/FileViewBase'
import FileViewList from '@/components/FileViewList'

export default {
  name: 'file-view-list',
  extends: FileViewBase,

  components: {
    FileViewList
  },

  props: {
    nested: Boolean
  },

  data: () => ({
    expanded: {}
  }),

  computed: {
    ...mapState(['unique', 'org'])
  },

  methods: {
    async beforeRefresh() {
      this.expanded = {}
    },

    async expandLocked(folder) {
      const unlocked = await this.unlockFolder(folder)
      if (unlocked) {
        this.toggleFolder(folder)
      }
    },

    async toggleFolder(folder, locked) {
      if (locked) {
        const unlocked = await this.unlockFolder(folder)
        if (!unlocked) return
      }

      if (this.expanded[folder] === undefined) {
        this.$set(this.expanded, folder, false)
      }

      this.expanded[folder] = !this.expanded[folder]
    }
  }
}
</script>

<style lang="scss">
.file-view-list {
  .file {
    @apply flex items-center w-full;
  }

  li:not(:last-child) {
    @apply border-b;
  }

  .icon {
    font-size: 2rem;
  }

  .expanded {
    transform: rotate(90deg);
  }
}
</style>
