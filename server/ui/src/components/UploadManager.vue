<template>
  <div v-if="uploads.length" class="upload-manager rounded shadow">
    <div class="sticky top-0 bg-primary text-white">
      <div class="flex p-2">
        <span class="mr-auto font-bold">
          {{ uploads.length | pluralize('Upload') }}
          ({{ Math.floor(totalPercent) }}%)
        </span>
        <button class="px-2" @click="clearAll">clear all</button>
        <button class="px-2" @click="minimized = !minimized">
          <fa-icon :icon="minimized ? 'angle-up' : 'angle-down'" />
        </button>
      </div>
      <div class="overflow-hidden h-1 bg-gray-400">
        <div
          :style="{ width: `${totalPercent}%` }"
          class="h-full bg-secondary"
        ></div>
      </div>
    </div>
    <div v-if="!minimized">
      <ul class="text-left">
        <li v-for="upload in uploads" class="border-b">
          <div class="flex">
            <div class="flex-grow p-2 pr-0">
              <div class="flex">
                <div
                  :title="`\u200e${upload.path}${upload.file.name}`"
                  class="upload-name mr-auto"
                >
                  &lrm;{{ upload.path + upload.file.name }}
                </div>
                <div>{{ Math.floor(100 * upload.progress) }}%</div>
              </div>
              <div class="overflow-hidden h-1 rounded bg-gray-400">
                <div
                  :class="
                    upload.error
                      ? 'bg-red-500'
                      : upload.done
                      ? 'bg-green-500'
                      : 'bg-secondary'
                  "
                  :style="{ width: `${100 * upload.progress}%` }"
                  class="h-full"
                ></div>
              </div>
            </div>
            <div class="flex items-center">
              <button
                class="px-4 text-gray-600 hover:text-black"
                @click="removeUpload(upload)"
              >
                <fa-icon icon="times" />
              </button>
            </div>
          </div>
        </li>
      </ul>
    </div>
  </div>
</template>

<script>
import API from '@/api'

const CHUNK_SIZE = 10 * 1024 ** 2 // 10 MB

export default {
  data: () => ({
    minimized: true,
    uploads: []
  }),

  computed: {
    isUploading() {
      return this.uploads.some(upload => !upload.done)
    },

    totalPercent() {
      let loaded = 0
      let total = 0
      this.uploads.forEach(upload => {
        const size = upload.file.size
        loaded += upload.progress * size
        total += size
      })
      return (100 * loaded) / total
    }
  },

  mounted() {
    this.$root.$on('upload', this.addUpload)
    this.$once('hook:beforeDestroy', () => {
      this.$root.$off('upload', this.addUpload)
    })

    window.addEventListener('beforeunload', e => {
      if (this.isUploading) {
        const msg = 'You have unfinished uploads'
        e.preventDefault()
        e.returnValue = msg
        return msg
      }
    })
  },

  methods: {
    addUpload({ path, files }) {
      for (let file of files) {
        const lastSlash = file.name.lastIndexOf('/') + 1
        const subpath = path + file.name.slice(0, lastSlash)
        const name = file.name.slice(lastSlash)
        file = new File([file], name, { type: file.type })

        const upload = {
          file,
          path: subpath,
          chunk: 0,
          progress: 0,
          error: false,
          done: false,
          cancel: () => {}
        }

        if (file.size < CHUNK_SIZE) {
          this.uploadFile(upload)
        } else {
          this.uploadChunks(upload)
        }
        this.uploads.push(upload)
      }
    },

    async clearAll() {
      if (this.isUploading) {
        const confirm = await this.$modal.confirm({
          title: 'Cancel All',
          body: 'There are still some uploads in progress. Are you sure you want to cancel them?',
          okClass: 'danger',
          okTitle: 'cancel all',
          cancelClass: '',
          cancelTitle: 'keep uploading'
        })
        if (!confirm) return
      }

      // slice to copy before mutating
      this.uploads.slice().forEach(upload => {
        this.removeUpload(upload)
      })
    },

    handleUploadResponse(res, upload) {
      if (res.code === 200 && (!res.failed || !res.failed.length)) return
      const msg = res.error
        ? res.error.message
        : res.failed && res.failed.length
        ? 'File was unable to be converted'
        : 'An unknown error occurred'
      this.$modal.alert({
        title: 'Upload Failed',
        body: msg
      })
      upload.progress = 1
      upload.error = true
      upload.done = true
      throw new Error('Upload failed')
    },

    async removeUpload(upload) {
      if (!upload.done) {
        upload.done = true
        upload.cancel()
      }

      const index = this.uploads.indexOf(upload)
      if (index !== -1) this.uploads.splice(index, 1)
    },

    async uploadChunks(upload) {
      try {
        const name = upload.file.name
        const size = upload.file.size
        const chunks = Math.ceil(size / CHUNK_SIZE)
        const res = await API.uploadInit(upload.path, name, size)
        this.handleUploadResponse(res, upload)
        const id = res.id

        while (upload.chunk < chunks) {
          const start = upload.chunk * CHUNK_SIZE
          const end = Math.min(start + CHUNK_SIZE, size)
          const chunk = upload.file.slice(start, end)
          const { promise, cancel } = API.uploadChunk({
            ...{ id, name, chunk, start, end, size },
            onProgress: e => (upload.progress = (start + e.loaded) / size)
          })
          upload.cancel = cancel
          const res = await promise
          this.handleUploadResponse(res, upload)
          upload.chunk++
        }

        upload.done = true
        this.$root.$emit('refresh')
      } catch (e) {
        console.error(e)
      }
    },

    async uploadFile(upload) {
      try {
        const { promise, cancel } = API.upload(
          upload.path,
          [upload.file],
          e => (upload.progress = e.loaded / e.total)
        )
        upload.cancel = cancel
        const res = await promise
        this.handleUploadResponse(res, upload)
        upload.done = true
        this.$root.$emit('refresh')
      } catch (e) {
        console.error(e)
      }
    }
  }
}
</script>

<style lang="scss" scoped>
.upload-manager {
  position: absolute;
  bottom: 1rem;
  right: 1rem;
  width: 100%;
  max-width: 24rem;
  max-height: 17rem;
  background-color: #fff;
  overflow-y: scroll;
}

.upload-name {
  width: 17em;
  direction: rtl;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
