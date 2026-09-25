<template>
  <div v-if="jobs.length" class="nanome2-imports">
    <div
      v-for="job in jobs"
      :key="job.id"
      class="card bg-white rounded shadow text-left p-3"
    >
      <div class="flex items-center">
        <span class="font-bold mr-auto" :class="titleClass(job)">
          {{ title(job) }}
        </span>
        <button
          v-if="job.state !== 'running'"
          class="px-2 text-gray-600 hover:text-black"
          title="close"
          @click="remove(job)"
        >
          <fa-icon icon="times" />
        </button>
      </div>
      <div class="text-gray-700 break-all">{{ job.path }}</div>

      <div class="overflow-hidden h-1 rounded bg-gray-400 my-2">
        <div
          class="h-full bar"
          :class="barClass(job)"
          :style="{ width: `${job.percent}%` }"
        ></div>
      </div>

      <p class="break-words">{{ job.message }}</p>

      <template v-if="job.result">
        <a
          v-if="isLink(job.result.url)"
          :href="job.result.url"
          target="_blank"
          rel="noopener"
          class="btn primary rounded inline-block my-2"
        >
          <fa-icon icon="external-link-alt" class="mr-1" />
          open the workspace
        </a>
        <p v-if="job.result.verification.text">
          {{ job.result.verification.text }}
        </p>
        <ul v-if="job.result.problems.length" class="text-red-600">
          <li v-for="p in job.result.problems" :key="p">
            Verification: {{ p }}
          </li>
        </ul>
        <ul v-if="job.result.warnings.length" class="text-yellow-800">
          <li v-for="w in job.result.warnings" :key="w">{{ w }}</li>
        </ul>
        <details v-if="job.result.notes.length">
          <summary>
            What the converter reports ({{ job.result.notes.length }})
          </summary>
          <pre>{{ job.result.notes.join('\n\n') }}</pre>
        </details>
        <details v-if="job.result.verification.notes.length">
          <summary>
            Differences Nanome 2 makes by design ({{
              job.result.verification.notes.length
            }})
          </summary>
          <pre>{{ job.result.verification.notes.join('\n') }}</pre>
        </details>
        <details v-if="job.result.summary">
          <summary>Full converter summary</summary>
          <pre>{{ job.result.summary }}</pre>
        </details>
      </template>

      <template v-if="job.error">
        <a
          v-if="isLink(job.error.partial.workspaceUrl)"
          :href="job.error.partial.workspaceUrl"
          target="_blank"
          rel="noopener"
          class="btn rounded inline-block my-2"
        >
          open the partly built workspace
        </a>
        <details v-if="job.error.body">
          <summary>
            Server response
            <template v-if="job.error.status">
              (HTTP {{ job.error.status }})
            </template>
          </summary>
          <pre>{{ job.error.body }}</pre>
        </details>
      </template>

      <details v-if="job.state !== 'running' && job.log.length">
        <summary>Progress log</summary>
        <pre>{{ job.log.join('\n') }}</pre>
      </details>
    </div>
  </div>
</template>

<script>
import { STEPS, openInNanome2 } from '@/nanome2'

let nextId = 1

export default {
  data: () => ({
    jobs: []
  }),

  computed: {
    running() {
      return this.jobs.some(job => job.state === 'running')
    }
  },

  mounted() {
    const warnOnLeave = e => {
      if (!this.running) return
      const msg = 'Open in Nanome 2 is still running and stops if you leave'
      e.preventDefault()
      e.returnValue = msg
      return msg
    }

    this.$root.$on('open-in-nanome2', this.start)
    window.addEventListener('beforeunload', warnOnLeave)
    this.$once('hook:beforeDestroy', () => {
      this.$root.$off('open-in-nanome2', this.start)
      window.removeEventListener('beforeunload', warnOnLeave)
    })
  },

  methods: {
    async start(paths) {
      const { nanome2 } = this.$store.state
      if (!nanome2) return

      if (!this.$store.state.token) {
        const loggedIn = await this.$modal.login({
          body: 'Open in Nanome 2 uses your Nanome account'
        })
        if (!loggedIn) return
      }

      for (const path of paths) {
        const busy = this.jobs.some(
          j => j.path === path && j.state === 'running'
        )
        if (!busy) this.run(path, nanome2)
      }
    },

    async run(path, { url, toolId }) {
      const job = {
        id: nextId++,
        path,
        state: 'running',
        message: 'Starting…',
        percent: 2,
        log: [],
        result: null,
        error: null
      }
      this.jobs.push(job)

      const onProgress = ({ step, message }) => {
        const at = STEPS.indexOf(step)
        if (at >= 0) {
          job.percent = Math.max(2, Math.round((100 * at) / (STEPS.length - 1)))
        }
        job.message = message
        job.log.push(`[${step}] ${message}`)
      }

      try {
        const result = await openInNanome2({
          path,
          token: this.$store.state.token,
          url,
          toolId,
          onProgress
        })
        this.finish(job, result)
      } catch (e) {
        this.fail(job, e)
      }
    },

    finish(job, result) {
      const verification = result.verification || {}
      const warnings = result.warnings || []
      job.result = {
        url: result.url,
        summary: result.summary || '',
        notes: result.notes || [],
        problems: verification.problems || [],
        warnings: warnings.filter(w => !w.startsWith('Verification: ')),
        verification: {
          text: verification.text || '',
          notes: verification.notes || []
        }
      }
      job.state = warnings.length ? 'warn' : 'ok'
      job.percent = 100
      const count = (n, what) => `${n} ${what}${n === 1 ? '' : 's'}`
      job.message =
        `Created "${result.workspaceName}": ` +
        `${count(result.entries.length, 'structure')}, ` +
        `${count(result.components, 'component')}, ` +
        `${count(result.annotations, 'annotation')}.`
    },

    fail(job, error) {
      console.error('Open in Nanome 2:', error)
      job.state = 'fail'
      job.percent = 100
      job.message = (error && error.message) || String(error)
      job.error = {
        status: error.status || null,
        body: error.body || '',
        partial: error.partial || {}
      }
    },

    remove(job) {
      this.jobs.splice(this.jobs.indexOf(job), 1)
    },

    isLink(url) {
      return typeof url === 'string' && /^https?:\/\//.test(url)
    },

    title(job) {
      return {
        running: 'Opening in Nanome 2',
        ok: 'Opened in Nanome 2',
        warn: 'Opened in Nanome 2, with warnings',
        fail: 'Could not open in Nanome 2'
      }[job.state]
    },

    titleClass(job) {
      return {
        ok: 'text-green-700',
        warn: 'text-yellow-800',
        fail: 'text-red-600'
      }[job.state]
    },

    barClass(job) {
      return {
        running: 'bg-secondary',
        ok: 'bg-green-500',
        warn: 'bg-yellow-500',
        fail: 'bg-red-500'
      }[job.state]
    }
  }
}
</script>

<style lang="scss" scoped>
.nanome2-imports {
  position: fixed;
  left: 1rem;
  bottom: 1rem;
  z-index: 40;
  width: calc(100vw - 2rem);
  max-width: 28rem;
  max-height: calc(100vh - 2rem);
  overflow-y: auto;
}

.card + .card {
  margin-top: 0.5rem;
}

.bar {
  transition: width 0.3s;
}

details {
  margin-top: 0.25rem;
}

summary {
  @apply text-secondary cursor-pointer;
}

pre {
  @apply bg-gray-100 rounded p-2 mt-1 text-xs overflow-auto;
  max-height: 16rem;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
