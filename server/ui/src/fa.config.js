import Vue from 'vue'
import { library } from '@fortawesome/fontawesome-svg-core'

import {
  FontAwesomeIcon,
  FontAwesomeLayers,
  FontAwesomeLayersText
} from '@fortawesome/vue-fontawesome'

Vue.component('fa-icon', FontAwesomeIcon)
Vue.component('fa-layers', FontAwesomeLayers)
Vue.component('fa-text', FontAwesomeLayersText)

import {
  faAngleRight,
  faArrowUp,
  faBars,
  faCloudUploadAlt,
  faFile,
  faFileDownload,
  faFolder,
  faFolderPlus,
  faLock,
  faLockOpen,
  faPen,
  faPlus,
  faSadTear,
  faSearch,
  faSitemap,
  faSyncAlt,
  faTh,
  faTrash
} from '@fortawesome/free-solid-svg-icons'

library.add({
  faAngleRight,
  faArrowUp,
  faBars,
  faCloudUploadAlt,
  faFile,
  faFileDownload,
  faFolder,
  faFolderPlus,
  faLock,
  faLockOpen,
  faPen,
  faPlus,
  faSadTear,
  faSearch,
  faSitemap,
  faSyncAlt,
  faTh,
  faTrash
})
