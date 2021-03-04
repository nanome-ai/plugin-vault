<template>
  <div
    v-if="!loading"
    class="file-view-grid pt-4 text-lg"
    :class="{ grid: files.length || folders.length }"
  >
    <template v-for="folder in folders">
      <a
        v-if="encrypted.includes(folder)"
        :key="folder"
        :title="folder"
        @dblclick="openLocked(folder)"
        @contextmenu.prevent="contextmenu($event, folder + '/', true)"
        class="cursor-default"
      >
        <fa-layers class="icon">
          <fa-icon icon="folder" />
          <fa-icon
            :icon="isLocked(folder) ? 'lock' : 'lock-open'"
            class="text-white"
            transform="down-1 shrink-11"
          />
        </fa-layers>
        <div class="truncate">{{ folder }}</div>
      </a>

      <router-link
        v-else
        :key="folder"
        :title="folder"
        :to="`${path}${folder}/`"
        @contextmenu.native.prevent="contextmenu($event, folder + '/')"
        event="dblclick"
        class="cursor-default"
      >
        <fa-icon icon="folder" class="icon pointer-events-none" />
        <div class="truncate">{{ folder }}</div>
      </router-link>
    </template>

    <template v-if="path == '/'">
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
      :title="file.full"
      @contextmenu.prevent="contextmenu($event, file.full)"
      @dblclick="$root.$emit('download', path + file.full)"
    >
      <fa-layers class="icon">
        <fa-icon icon="file" />
        <fa-text
          class="text-white"
          transform="down-4 shrink-12"
          :value="file.ext.substr(0, 4)"
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
}
</style>
