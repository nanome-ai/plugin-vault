<template>
  <input
    type="checkbox"
    class="select-box"
    :checked="checked"
    :aria-label="`select ${label}`"
    @click.stop="$emit('toggle')"
    @dblclick.stop
  />
</template>

<script>
// .stop: the item around it would otherwise treat the click as its own, and a
// folder link cancels clicks, which would undo the checkbox's own toggle
export default {
  props: {
    checked: Boolean,
    label: String
  }
}
</script>
