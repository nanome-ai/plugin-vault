<template>
  <div id="app" class="w-screen h-screen">
    <router-view />
    <UploadManager />
  </div>
</template>

<script>
import { mapState } from 'vuex'
import UploadManager from '@/components/UploadManager'

export default {
  components: { UploadManager },

  computed: mapState(['unique']),

  created() {
    const { query, path } = this.$route
    if (!this.unique && query.auth) {
      const data = { token: query.auth }
      this.$store.commit('PATCH_USER', data)
      this.$store.dispatch('refresh')
      this.$router.replace({ path })
    }
  }
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
