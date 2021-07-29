<template>
  <div
    v-show="showDropzone || isUploading"
    @dragover.prevent
    @dragenter.prevent="isHovering = true"
    @dragleave.prevent.self="isHovering = false"
    @drop.prevent="onDrop"
    class="file-dropzone"
    :class="{ hover: isHovering }"
  >
    <label
      v-if="showDropzone || isUploading"
      v-click-out="hide"
      class="message m-4"
    >
      <input
        class="visually-hidden"
        @change="onChange"
        :accept="allExtensions | extensions"
        type="file"
        multiple
      />
      <div class="text-4xl">
        <template v-if="isUploading">
          Uploading {{ isConverting ? 'and converting' : '' }} files...
        </template>
        <template v-else-if="!numDropping">
          Drop items or
          <span class="text-blue-500">click</span>
          to upload
        </template>
        <template v-else>
          Drop {{ numDropping }} item{{ numDropping > 1 ? 's' : '' }} here to
          upload
        </template>
      </div>
      <button
        v-if="!numDropping && !isUploading"
        @click="hide"
        class="link text-2xl text-red-500"
      >
        cancel
      </button>
    </label>
  </div>
</template>

<script>
import { mapGetters, mapState } from 'vuex'
import API from '@/api'
import { getFiles } from '@/helpers/files'

export default {
  props: {
    path: String
  },

  data: () => ({
    showDropzone: false,
    isHovering: false,
    isConverting: false,
    isUploading: false,
    numDropping: 0,
    numEvents: 0
  }),

  computed: {
    ...mapGetters(['allExtensions']),
    ...mapState(['extensions'])
  },

  created() {
    document.body.addEventListener('dragenter', this.onDragEnter)
    document.body.addEventListener('dragleave', this.onDragLeave)
  },

  destroyed() {
    document.body.removeEventListener('dragenter', this.onDragEnter)
    document.body.removeEventListener('dragleave', this.onDragLeave)
  },

  methods: {
    onDragEnter(e) {
      this.numEvents++
      this.numDropping = e.dataTransfer.items.length
      this.showDropzone = true
    },

    onDragLeave(e) {
      this.numEvents--
      if (this.numEvents) return
      this.showDropzone = false
      this.numDropping = 0
    },

    async onDrop(e) {
      this.isHovering = false
      const files = await getFiles(e)
      await this.upload(files)
      this.numDropping = 0
    },

    async onChange(e) {
      const files = e.target.files
      await this.upload(files)
      e.target.value = null
      this.numDropping = 0
    },

    async upload(files) {
      this.isUploading = true

      const skipped = []
      const upload = []
      const convert = []
      for (const file of files) {
        const isSupported = this.allExtensions.some(ext => {
          return file.name.toLowerCase().endsWith('.' + ext)
        })
        isSupported ? upload.push(file) : skipped.push(file)

        const needsConvert = this.extensions.converted.some(ext => {
          return file.name.toLowerCase().endsWith('.' + ext)
        })
        if (needsConvert) convert.push(file)
      }

      let confirmUpload = true
      if (convert.length) {
        const list = convert.map(f => f.name).join('<br>')
        confirmUpload = await this.$modal.confirm({
          title: `Convert to PDF`,
          body:
            `Files will be converted to PDF:<br>${list}` +
            '<br><br><b>NOTE:</b> This can take a while.',
          okTitle: 'upload'
        })
        this.isConverting = true
      }

      if (upload.length && confirmUpload) {
        const path = this.path === '/' ? '/shared/' : this.path
        const res = await API.upload(path, upload)

        if (res.code !== 200) {
          this.$modal.alert({
            title: 'Upload Failed',
            body: res.error.message
          })
        } else {
          if (res.failed) {
            const list = res.failed.join('<br>')
            this.$modal.alert({
              title: 'Convert Failed',
              body: `Files were unable to be converted:<br>${list}`
            })
          }
          if (path !== this.path) {
            this.$router.push(path)
          }
        }
        this.$emit('upload')
      }

      this.isConverting = false
      this.isUploading = false
      this.showDropzone = false

      if (!upload.length) {
        this.$modal.alert({
          title: 'Skipping Upload',
          body: 'No supported files found'
        })
      } else if (skipped.length) {
        const list = skipped.map(f => f.name).join('<br>')
        this.$modal.alert({
          title: 'Files Skipped',
          body: `${skipped.length} unsupported files skipped:<br>${list}`
        })
      }
    },

    show() {
      this.showDropzone = true
    },

    hide() {
      this.showDropzone = false
    }
  }
}
</script>

<style lang="scss">
.file-dropzone {
  @apply absolute inset-0 bg-gray-200 rounded;

  &.hover {
    @apply bg-gray-300;

    * {
      pointer-events: none;
    }
  }

  .message {
    @apply absolute inset-0 border-4 border-gray-700 border-dashed rounded;
    @apply flex flex-col items-center justify-center;
    cursor: pointer;
  }
}
</style>
