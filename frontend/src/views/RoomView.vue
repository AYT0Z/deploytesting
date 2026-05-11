<script setup>
import { computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import VideoSyncPlayer from '@/components/VideoSyncPlayer.vue'
import { useRoomStore } from '@/stores/room'

const route = useRoute()
const rooms = useRoomStore()

const shareUrl = computed(() => `${window.location.origin}${route.fullPath}`)

onMounted(async () => {
  await rooms.fetchRoom(route.params.slug)
})

watch(
  () => route.params.slug,
  async (slug) => {
    if (slug) await rooms.fetchRoom(slug)
  },
)
</script>

<template>
  <div>
    <v-btn to="/" variant="text" class="mb-4">← На главную</v-btn>

    <v-progress-linear v-if="rooms.loading" indeterminate color="primary" class="mb-4" />

    <v-alert v-if="rooms.error" type="warning" variant="tonal" class="mb-4">
      {{ rooms.error }}
    </v-alert>

    <template v-else-if="rooms.current">
      <h1 class="headline mb-2">{{ rooms.current.title || 'Комната ' + rooms.current.slug }}</h1>
      <p class="sub mb-6">
        Поделитесь ссылкой:
        <code class="link">{{ shareUrl }}</code>
      </p>
      <VideoSyncPlayer :room="rooms.current" />
    </template>
  </div>
</template>

<style scoped>
.headline {
  font-size: 1.5rem;
  font-weight: 600;
}
.sub {
  color: rgba(255, 255, 255, 0.68);
}
.link {
  color: #b39cff;
  word-break: break-all;
}
</style>
