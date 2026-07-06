<script setup lang="ts">
defineProps<{
  id: string
}>()
</script>

<template>
  <div class="session-view">
    <p>sessione {{ id }}</p>
  </div>
</template>

<style scoped>
.session-view {
  padding: 2rem;
  color: #ccc;
}
</style>
