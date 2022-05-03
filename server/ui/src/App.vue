<template>
  <div id="app" class="w-screen h-screen">
    <router-view />
    <UploadManager />
  </div>
</template>

<script>
import UploadManager from '@/components/UploadManager'

export default {
  components: { UploadManager }
}
</script>

<style lang="scss">
:root {
  --primary: #0e0f32;
  --secondary: #2e70bf;
}

body {
  background-color: var(--primary);
}

#app {
  font-family: 'Avenir', Helvetica, Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  text-align: center;
  color: var(--primary);
}
</style>
