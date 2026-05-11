<script setup>
import { RouterView } from 'vue-router'
</script>

<template>
  <v-app class="app-root">
    <v-app-bar flat color="surface" density="comfortable">
      <v-toolbar-title class="title">
        <router-link to="/" class="brand">WatchTogether</router-link>
      </v-toolbar-title>
      <v-spacer />
    </v-app-bar>
    <v-main>
      <v-container class="py-8" max-width="960">
        <RouterView />
      </v-container>
    </v-main>
  </v-app>
</template>

<style>
html,
body,
#app {
  height: 100%;
}
.app-root {
  min-height: 100vh;
  background: radial-gradient(1200px 600px at 20% -10%, #2a1f4a 0%, #0e0e14 55%);
}
.brand {
  color: inherit;
  text-decoration: none;
  font-weight: 600;
  letter-spacing: 0.02em;
}
.title {
  font-size: 1.15rem;
}
</style>
