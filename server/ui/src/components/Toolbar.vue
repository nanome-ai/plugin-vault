<template>
  <div class="toolbar flex flex-wrap text-lg items-center">
    <div class="toggle relative mr-2 flex">
      <input
        @input="$emit('display-mode', $event.target.value)"
        checked
        value="grid"
        type="radio"
        name="display-mode"
        id="display-mode-grid"
      />
      <label for="display-mode-grid" class="btn rounded-l" title="grid view">
        <fa-icon icon="th" />
      </label>
      <input
        @input="$emit('display-mode', $event.target.value)"
        value="list"
        type="radio"
        name="display-mode"
        id="display-mode-list"
      />
      <label for="display-mode-list" class="btn rounded-r" title="list view">
        <fa-icon icon="bars" />
      </label>
    </div>
    <button
      @click="$root.$emit('refresh')"
      class="btn rounded mr-2"
      title="refresh"
    >
      <fa-icon icon="sync-alt" />
      <span class="hidden ml-1 lg:inline"> refresh</span>
    </button>
    <button
      @click="$emit('new-folder')"
      class="btn rounded mr-2"
      title="new folder"
    >
      <fa-layers>
        <fa-icon icon="folder" />
        <fa-icon icon="plus" transform="down-1 shrink-10" class="text-white" />
      </fa-layers>
      <span class="hidden ml-1 lg:inline"> new folder</span>
    </button>
    <button @click="$emit('show-upload')" class="btn rounded" title="upload">
      <fa-icon icon="cloud-upload-alt" />
      <span class="hidden ml-1 lg:inline"> upload</span>
    </button>
    <div v-if="folderItems.length" class="flex items-center ml-auto">
      <label
        class="select-all btn rounded flex items-center"
        :title="count ? 'clear selection' : 'select all'"
      >
        <input
          type="checkbox"
          class="select-box"
          :checked="count > 0"
          :indeterminate.prop="count > 0 && !allSelected"
          @change="toggleAll"
        />
        <span class="ml-2" :class="{ 'hidden sm:inline': !count }">
          {{ count ? `${count} selected` : 'select all' }}
        </span>
      </label>
      <button
        v-if="count"
        @click="$emit('download-selection')"
        class="btn primary rounded ml-2"
        title="download selected"
      >
        <fa-icon icon="file-download" />
        <span class="ml-1"> download</span>
      </button>
    </div>
    <!-- <div class="flex-grow"></div>
    <div class="search relative">
      <input
        type="search"
        @input="$emit('search', $event.target.value)"
        class="border rounded py-2 px-3"
        placeholder="search..."
      />
      <fa-icon icon="search" class="absolute text-gray-400 icon" />
    </div> -->
  </div>
</template>

<script>
import { mapState } from 'vuex'

export default {
  computed: {
    ...mapState(['selection', 'folderItems']),

    count() {
      return this.selection.items.length
    },

    allSelected() {
      const { folder, items } = this.selection
      return (
        folder === this.$route.path && items.length === this.folderItems.length
      )
    }
  },

  methods: {
    toggleAll() {
      if (this.count) {
        this.$store.commit('CLEAR_SELECTION')
      } else {
        this.$store.commit('SELECT', {
          folder: this.$route.path,
          items: this.folderItems.slice()
        })
      }
    }
  }
}
</script>

<style lang="scss">
.toolbar {
  // the selection controls move to their own row on narrow screens
  row-gap: 0.5rem;

  .toggle {
    input {
      position: absolute !important;
      clip: rect(0, 0, 0, 0);
      height: 1px;
      width: 1px;
      border: 0;
      overflow: hidden;
    }

    label {
      cursor: pointer;
    }

    input:checked + label {
      @apply bg-gray-700 text-white;
    }
  }

  .select-all {
    cursor: pointer;
    user-select: none;
  }

  .search {
    .icon {
      top: 50%;
      left: 0.5em;
      transform: translateY(-50%);
    }

    input {
      padding-left: 2em;

      &:focus {
        outline: none;
      }

      &:focus + .icon {
        @apply text-gray-700;
      }
    }
  }
}
</style>
