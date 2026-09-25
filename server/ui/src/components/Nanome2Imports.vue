<template>
  <div>
    <div v-if="picker" class="modal" @click.self="closePicker">
      <div class="picker modal-body text-left" @keydown.esc="closePicker">
        <div class="p-4">
          <h2>Add to a Nanome 2 workspace</h2>
          <p class="text-gray-700 break-all">{{ picker.label }}</p>
          <input
            ref="filter"
            v-model="picker.filter"
            class="w-full mx-0 my-2"
            placeholder="filter workspaces"
            type="text"
          />
          <p v-if="picker.loading" class="py-2">Loading workspaces…</p>
          <p v-else-if="!picker.workspaces.length" class="py-2">
            No workspaces yet.
          </p>
          <ul v-else class="workspaces">
            <li v-for="w in filteredWorkspaces" :key="w.id">
              <button @click="choose(w)">
                <div class="truncate">{{ w.name }}</div>
                <div v-if="openedText(w)" class="text-sm text-gray-600">
                  {{ openedText(w) }}
                </div>
              </button>
            </li>
          </ul>
        </div>
        <div class="modal-actions">
          <button class="btn" @click="closePicker">cancel</button>
          <button class="btn primary" @click="choose(null)">
            new workspace
          </button>
        </div>
      </div>
    </div>

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
        <div class="text-gray-700 break-all">{{ job.label }}</div>

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
            open the workspace
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
  </div>
</template>

<script>
import {
  SESSION_STEPS,
  STRUCTURE_STEPS,
  listWorkspaces,
  loadStructures,
  openInNanome2
} from '@/nanome2'

let nextId = 1

const plural = (n, what) => `${n} ${what}${n === 1 ? '' : 's'}`

const TITLES = {
  session: {
    running: 'Opening in Nanome 2',
    ok: 'Opened in Nanome 2',
    warn: 'Opened in Nanome 2, with warnings',
    fail: 'Could not open in Nanome 2'
  },
  structures: {
    running: 'Loading into Nanome 2',
    ok: 'Loaded into Nanome 2',
    warn: 'Loaded into Nanome 2, with warnings',
    fail: 'Could not load into Nanome 2'
  }
}

export default {
  data: () => ({
    jobs: [],
    // { paths, label, workspaces, loading, filter } while choosing a workspace
    picker: null
  }),

  computed: {
    running() {
      return this.jobs.some(job => job.state === 'running')
    },

    filteredWorkspaces() {
      const filter = this.picker.filter.trim().toLowerCase()
      return this.picker.workspaces.filter(w =>
        String(w.name || '')
          .toLowerCase()
          .includes(filter)
      )
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

    this.$root.$on('open-in-nanome2', this.openSessions)
    this.$root.$on('load-in-nanome2', this.loadFiles)
    window.addEventListener('beforeunload', warnOnLeave)
    this.$once('hook:beforeDestroy', () => {
      this.$root.$off('open-in-nanome2', this.openSessions)
      this.$root.$off('load-in-nanome2', this.loadFiles)
      window.removeEventListener('beforeunload', warnOnLeave)
    })
  },

  methods: {
    async loggedIn() {
      if (this.$store.state.token) return true
      return this.$modal.login({
        body: 'Open in Nanome 2 uses your Nanome account'
      })
    },

    // v1 sessions: each becomes its own new workspace
    async openSessions(paths) {
      const { nanome2 } = this.$store.state
      if (!nanome2 || !(await this.loggedIn())) return

      for (const path of paths) {
        const busy = this.jobs.some(
          j => j.label === path && j.state === 'running'
        )
        if (busy) continue

        this.run('session', path, onProgress =>
          openInNanome2({
            path,
            token: this.$store.state.token,
            url: nanome2.url,
            toolId: nanome2.toolId,
            onProgress
          })
        )
      }
    },

    // structure files: all into one workspace, a new one unless `pick`
    async loadFiles({ paths, pick }) {
      if (!this.$store.state.nanome2 || !(await this.loggedIn())) return

      const label =
        paths.length === 1
          ? paths[0]
          : `${plural(paths.length, 'file')} in ${folderOf(paths[0])}`
      if (!pick) return this.load(paths, label, null)

      this.picker = { paths, label, workspaces: [], loading: true, filter: '' }
      this.$nextTick(() => this.$refs.filter && this.$refs.filter.focus())
      try {
        const workspaces = await listWorkspaces({
          token: this.$store.state.token,
          url: this.$store.state.nanome2.url
        })
        if (this.picker) {
          this.picker.workspaces = workspaces
          this.picker.loading = false
        }
      } catch (e) {
        this.picker = null
        this.$modal.alert({
          title: 'Could Not List Workspaces',
          body: escapeHtml((e && e.message) || String(e))
        })
      }
    },

    choose(workspace) {
      const { paths, label } = this.picker
      this.picker = null
      this.load(paths, label, workspace)
    },

    closePicker() {
      this.picker = null
    },

    load(paths, label, workspace) {
      const first = paths[0].split('/').pop()
      const name =
        paths.length === 1
          ? first.replace(/\.[^.]+$/, '')
          : folderOf(paths[0])
              .replace(/\/$/, '')
              .split('/')
              .pop() || 'Vault'

      this.run('structures', label, onProgress =>
        loadStructures({
          paths,
          token: this.$store.state.token,
          url: this.$store.state.nanome2.url,
          workspace,
          name,
          onProgress
        })
      )
    },

    async run(kind, label, start) {
      const steps = kind === 'session' ? SESSION_STEPS : STRUCTURE_STEPS
      const job = {
        id: nextId++,
        kind,
        label,
        state: 'running',
        message: 'Starting…',
        percent: 2,
        log: [],
        result: null,
        error: null
      }
      this.jobs.push(job)

      const onProgress = ({ step, message }) => {
        const at = steps.indexOf(step)
        if (at >= 0) {
          job.percent = Math.max(2, Math.round((100 * at) / (steps.length - 1)))
        }
        job.message = message
        job.log.push(`[${step}] ${message}`)
      }

      try {
        const result = await start(onProgress)
        if (kind === 'session') this.finishSession(job, result)
        else this.finishStructures(job, result)
      } catch (e) {
        this.fail(job, e)
      }
    },

    finishSession(job, result) {
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
      job.message =
        `Created "${result.workspaceName}": ` +
        `${plural(result.entries.length, 'structure')}, ` +
        `${plural(result.components, 'component')}, ` +
        `${plural(result.annotations, 'annotation')}.`
    },

    finishStructures(job, result) {
      job.result = {
        url: result.url,
        summary: '',
        notes: [],
        problems: [],
        warnings: [],
        verification: { text: '', notes: [] }
      }
      job.state = 'ok'
      job.percent = 100
      const loaded = plural(result.entries.length, 'structure')
      job.message = result.existing
        ? `Added ${loaded} to "${result.workspaceName}".`
        : `Created "${result.workspaceName}" with ${loaded}.`
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

    openedText(workspace) {
      const when = workspace.lastAccessedAt || workspace.updatedAt
      const date = when && new Date(when)
      if (!date || isNaN(date)) return ''
      return `last opened ${date.toLocaleDateString()}`
    },

    title(job) {
      return TITLES[job.kind][job.state]
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

const folderOf = path => path.slice(0, path.lastIndexOf('/') + 1)

const escapeHtml = text =>
  String(text).replace(
    /[&<>"']/g,
    c =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[
        c
      ])
  )
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

.picker.modal-body {
  width: calc(100vw - 2rem);
  max-width: 28rem;
}

.workspaces {
  max-height: 16rem;
  overflow-y: auto;

  button {
    @apply block w-full text-left px-2 py-1 rounded;

    &:hover,
    &:focus {
      @apply bg-gray-200 outline-none;
    }
  }
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
