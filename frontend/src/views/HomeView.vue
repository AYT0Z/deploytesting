<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useRoomStore } from '@/stores/room'

const router = useRouter()
const auth = useAuthStore()
const rooms = useRoomStore()

const tab = ref(0)
const loginForm = ref({ username: '', password: '' })
const regForm = ref({ username: '', password: '', email: '' })
const roomForm = ref({ title: '', video_url: '' })
const busy = ref(false)
const error = ref('')

async function onLogin() {
  error.value = ''
  busy.value = true
  try {
    await auth.login(loginForm.value)
  } catch (e) {
    error.value = e.response?.data?.detail || 'Ошибка входа'
  } finally {
    busy.value = false
  }
}

async function onRegister() {
  error.value = ''
  busy.value = true
  try {
    await auth.register(regForm.value)
  } catch (e) {
    const d = e.response?.data
    error.value =
      (typeof d === 'object' && d && (d.username?.[0] || d.password?.[0])) || 'Ошибка регистрации'
  } finally {
    busy.value = false
  }
}

async function onCreateRoom() {
  error.value = ''
  busy.value = true
  try {
    const data = await rooms.createRoom({
      title: roomForm.value.title,
      video_url: roomForm.value.video_url,
    })
    await router.push({ name: 'room', params: { slug: data.slug } })
  } catch (e) {
    const d = e.response?.data
    if (typeof d === 'object' && d) {
      error.value = d.video_url?.[0] || d.detail || JSON.stringify(d)
    } else {
      error.value = 'Не удалось создать комнату'
    }
  } finally {
    busy.value = false
  }
}

function logout() {
  auth.logout()
}
</script>

<template>
  <div>
    <h1 class="headline mb-2">Совместный просмотр</h1>
    <p class="sub mb-8">
      Создайте комнату и отправьте ссылку друзьям. Поддерживаются Rutube, YouTube.
    </p>

    <v-alert v-if="error" type="error" variant="tonal" class="mb-4" closable @click:close="error = ''">
      {{ error }}
    </v-alert>

    <template v-if="!auth.isAuthenticated">
      <v-tabs v-model="tab" class="mb-4" color="primary">
        <v-tab>Вход</v-tab>
        <v-tab>Регистрация</v-tab>
      </v-tabs>

      <v-window v-model="tab">
        <v-window-item>
          <v-card variant="tonal" class="pa-4">
            <v-form @submit.prevent="onLogin">
              <v-text-field v-model="loginForm.username" label="Логин" autocomplete="username" />
              <v-text-field
                v-model="loginForm.password"
                label="Пароль"
                type="password"
                autocomplete="current-password"
              />
              <v-btn type="submit" color="primary" :loading="busy">Войти</v-btn>
            </v-form>
          </v-card>
        </v-window-item>

        <v-window-item>
          <v-card variant="tonal" class="pa-4">
            <v-form @submit.prevent="onRegister">
              <v-text-field v-model="regForm.username" label="Логин" autocomplete="username" />
              <v-text-field v-model="regForm.email" label="Email (необязательно)" type="email" />
              <v-text-field
                v-model="regForm.password"
                label="Пароль (мин. 8 символов)"
                type="password"
                autocomplete="new-password"
              />
              <v-btn type="submit" color="primary" :loading="busy">Зарегистрироваться</v-btn>
            </v-form>
          </v-card>
        </v-window-item>
      </v-window>
    </template>

    <template v-else>
      <v-card variant="tonal" class="pa-4">
        <p class="mb-4 text-medium-emphasis">
          Вы вошли как <strong>{{ auth.username }}</strong>
          <v-btn variant="text" size="small" class="ml-2" @click="logout">Выйти</v-btn>
        </p>
        <v-form @submit.prevent="onCreateRoom">
          <v-text-field v-model="roomForm.title" label="Название комнаты (необязательно)" />
          <v-text-field
            v-model="roomForm.video_url"
            label="Ссылка на видео"
            placeholder="https://rutube.ru/video/... или прямой .mp4"
            required
          />
          <v-btn type="submit" color="primary" :loading="busy">Создать и открыть</v-btn>
        </v-form>
      </v-card>
    </template>
  </div>
</template>

<style scoped>
.headline {
  font-size: 1.75rem;
  font-weight: 600;
}
.sub {
  color: rgba(255, 255, 255, 0.68);
  line-height: 1.6;
}
</style>
