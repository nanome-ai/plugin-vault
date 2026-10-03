<template>
  <div
    v-if="!loading"
    class="file-view-grid pt-4 text-lg"
    :class="{
      grid: files.length || folders.length,
      selecting: selected.length
    }"
  >
    <template v-for="folder in folders">
      <a
        v-if="encrypted.includes(folder.name)"
        :key="folder.name"
        :title="`${folder.name} (${folder.size_text})`"
        :class="{ selected: isSelected(folder.name + '/') }"
        data-select
        @click="select($event, folder.name + '/')"
        @dblclick="openLocked(folder.name)"
        @contextmenu.prevent="contextmenu($event, folder.name + '/', true)"
        class="item cursor-default"
      >
        <select-box
          v-if="selectable"
          :checked="isSelected(folder.name + '/')"
          :label="folder.name"
          @toggle="toggleSelect(folder.name + '/')"
        />
        <fa-layers class="icon">
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
        :key="folder.name"
        :title="`${folder.name} (${folder.size_text})`"
        :to="`${path}${folder.name}/`"
        :class="{ selected: isSelected(folder.name + '/') }"
        data-select
        @click.native="select($event, folder.name + '/')"
        @contextmenu.native.prevent="contextmenu($event, folder.name + '/')"
        event="dblclick"
        class="item cursor-default"
      >
        <select-box
          v-if="selectable"
          :checked="isSelected(folder.name + '/')"
          :label="folder.name"
          @toggle="toggleSelect(folder.name + '/')"
        />
        <fa-icon icon="folder" class="icon pointer-events-none" />
        <div class="truncate">{{ folder.name }}</div>
      </router-link>
    </template>

    <template v-if="path == '/'">
      <router-link
        v-if="$store.state.org"
        to="/my-org/"
        @contextmenu.native.prevent="contextmenu($event, 'my-org/')"
        event="dblclick"
        class="cursor-default"
      >
        <fa-layers class="icon">
          <fa-icon icon="folder" />
          <fa-icon
            icon="sitemap"
            class="text-white"
            transform="down-1 left-2 shrink-11"
          />
        </fa-layers>
        <div>my org</div>
      </router-link>

      <a v-if="!$store.state.unique" @dblclick="$modal.login()">
        <fa-layers class="icon">
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
        class="cursor-default"
      >
        <fa-layers class="icon">
          <fa-icon icon="folder" />
          <fa-icon
            icon="lock-open"
            class="text-white"
            transform="down-1 shrink-11"
          />
        </fa-layers>
        <div>account</div>
      </router-link>
    </template>

    <div
      v-for="file in files"
      :key="file.full"
      :title="`${file.full} (${file.size_text})`"
      :class="{ selected: isSelected(file.full) }"
      class="item"
      data-select
      @click="select($event, file.full)"
      @contextmenu.prevent="contextmenu($event, file.full)"
      @dblclick="$root.$emit('download', path + file.full)"
    >
      <select-box
        v-if="selectable"
        :checked="isSelected(file.full)"
        :label="file.full"
        @toggle="toggleSelect(file.full)"
      />
      <fa-layers class="icon">
        <fa-icon icon="file" />
        <fa-text
          class="text-white"
          :transform="'down-4 shrink-' + (file.ext.length < 5 ? 12 : 13)"
          :value="file.ext"
        />
      </fa-layers>
      <div class="truncate">{{ file.name }}</div>
    </div>

    <div v-if="!files.length && !folders.length" class="text-xl py-4">
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
import FileViewBase from '@/components/FileViewBase'

export default {
  extends: FileViewBase
}
</script>

<style lang="scss">
.file-view-grid {
  grid-template-columns: repeat(auto-fill, minmax(7rem, 1fr));

  .icon {
    font-size: 4rem;
  }

  .item {
    @apply relative rounded p-1;
  }

  .item.selected {
    background-color: rgba(46, 112, 191, 0.15);
    box-shadow: inset 0 0 0 2px var(--secondary);
  }

  // shown on hover, and on every item once something is selected
  .select-box {
    @apply absolute top-0 left-0 m-2 opacity-0;
  }

  .item:hover .select-box,
  .item.selected .select-box,
  &.selecting .select-box,
  .select-box:focus {
    @apply opacity-100;
  }
}
</style>
