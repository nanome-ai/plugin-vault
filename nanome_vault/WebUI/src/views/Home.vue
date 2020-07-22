<template>
  <div class="home min-h-full container m-auto bg-white flex flex-col">
    <header class="mb-4 mx-auto text-white">
      <div class="inline-flex items-baseline text-5xl">
        <img class="mr-4" src="@/assets/logo.png" /> Vault
      </div>
    </header>
    <h1 class="font-bold">Upload Files to Nanome</h1>

    <div v-if="authEnabled && !token">
      <p class="text-lg mt-4 mb-8">
        Access shared content from the community <br />or share your own with
        people in your Nanome sessions.
      </p>
      <button @click="$modal.login()" class="text-3xl btn primary rounded-lg">
        <div class="my-2 mx-8">
          <fa-icon class="mr-2" icon="lock" />
          Access Vault
        </div>
      </button>
    </div>

    <template v-else>
      <p class="text-lg mb-8">
        Drag and drop or click the new file button to upload files.<br />
        Supports <b>{{ extensions.supported | extensions }}</b>
        <br />
        Converts to PDF <b>{{ extensions.converted | extensions }}</b>
      </p>

      <div class="text-left">
        <div class="text-lg px-4 py-2 ml-4 rounded bg-gray-200 inline">
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
  width: 100%;

  padding: 2em 0 4em;
  background: radial-gradient(
    circle at 50% -450px,
    var(--primary) 600px,
    transparent 601px
  );

  img {
    height: 1em;
  }
}
</style>
