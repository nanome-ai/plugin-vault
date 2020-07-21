<template>
  <div class="home min-h-full container m-auto bg-white flex flex-col">
    <header class="pt-10 mx-auto">
      <h1 class="inline-flex items-baseline">
        <img class="mr-4" src="@/assets/logo.png" /> Vault
      </h1>
      <h2>Upload files to make them available in Nanome!</h2>
    </header>

    <p class="text-lg pt-2 pb-4">
      Drag and drop or click the new file button to upload files.<br />
      Supports <b>{{ extensions.supported | extensions }}</b>
      <br />
      Converts to PDF <b>{{ extensions.converted | extensions }}</b>
    </p>

    <div v-if="authEnabled && !token">
      <button @click="$modal.login()" class="text-4xl btn rounded-lg mt-32">
        <div class="my-5 mx-24">
          <fa-icon class="text-6xl" icon="lock" />
          <div>Access Vault</div>
        </div>
      </button>
    </div>

    <template v-else>
      <div class="text-left">
        <div
          class="text-lg text-left px-4 py-2 ml-4 rounded bg-gray-200 inline"
        >
          <template v-if="name">
            Welcome <b>{{ name }}!</b>&nbsp;
            <a @click="$store.dispatch('logout')" class="link text-red-500"
              >log out</a
            >
          </template>
          <template v-else>
            Welcome!
            <a @click="$modal.login()" class="link text-blue-500">log in</a>
          </template>
        </div>
      </div>

      <file-explorer />
    </template>
  </div>
</template>

<script>
import { mapState } from 'vuex'
import FileExplorer from '@/components/FileExplorer'

export default {
  components: { FileExplorer },
  computed: mapState(['authEnabled', 'token', 'name', 'extensions'])
}
</script>

<style lang="scss">
header {
  img {
    height: 1em;
  }
}
</style>
