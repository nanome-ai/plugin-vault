<template>
  <div v-if="nanome2 && !dismissed" class="nanome2-banner">
    <p>
      Vault works with <b>Nanome Classic</b> (v1.24). <b>Nanome 2</b>, the
      latest version of Nanome, is at
      <a :href="nanome2.url" target="_blank" rel="noopener">{{ host }}</a
      >.
    </p>
    <p>
      Structure files (.pdb, .cif, .sdf and more) and Classic sessions open in
      Nanome 2 from their right-click menu.
    </p>
    <button class="close" title="close" @click="dismiss">
      <fa-icon icon="times" />
    </button>
  </div>
</template>

<script>
import { mapState } from 'vuex'

const KEY = 'nanome2-banner-dismissed'

export default {
  data: () => ({ dismissed: false }),

  computed: {
    ...mapState(['nanome2']),

    host() {
      return this.nanome2.url.replace(/^https?:\/\//, '')
    }
  },

  created() {
    try {
      this.dismissed = localStorage.getItem(KEY) === '1'
    } catch (e) {}
  },

  methods: {
    dismiss() {
      this.dismissed = true
      try {
        localStorage.setItem(KEY, '1')
      } catch (e) {}
    }
  }
}
</script>

<style lang="scss" scoped>
// padded on both sides so the text stays centered next to the close button
.nanome2-banner {
  @apply relative bg-secondary text-white text-center py-2 px-10;

  a {
    @apply underline font-bold;
  }

  .close {
    @apply absolute top-0 right-0 px-3 py-2 opacity-75;

    &:hover {
      @apply opacity-100;
    }
  }
}
</style>
