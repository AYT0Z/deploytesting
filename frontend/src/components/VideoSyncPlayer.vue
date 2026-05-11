<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import videojs from 'video.js'
import 'video.js/dist/video-js.css'
import { useAuthStore } from '@/stores/auth'

/** Допустимое расхождение по времени (сек): мельче — не делаем seek / не перезагружаем embed */
const SYNC_TOLERANCE_SEC = 1.5

/** Периодическая синхронизация от ведущего (сек) — подтягивает гостей после локальной паузы/воспроизведения */
const HOST_TICK_MS = 1800
const PRESENCE_PING_MS = 7000
const PRESENCE_STALE_MS = 20000
const CHAT_HISTORY_LIMIT = 200

const props = defineProps({
  room: { type: Object, required: true },
})

const auth = useAuthStore()

const directEl = ref(null)
const iframeEl = ref(null)
const embedWrap = ref(null)
const ytHost = ref(null)
const ytWrap = ref(null)
const ytGuestVolume = ref(100)

let vjs = null
let ytPlayer = null
let ws = null
let hostTickTimer = null
let presencePingTimer = null
let presenceSweepTimer = null
const applying = ref(false)
const connected = ref(false)
function createClientId() {
  try {
    if (window.crypto?.randomUUID) return window.crypto.randomUUID()
  } catch {
    /* ignore */
  }
  try {
    if (window.crypto?.getRandomValues) {
      const bytes = new Uint8Array(16)
      window.crypto.getRandomValues(bytes)
      return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')
    }
  } catch {
    /* ignore */
  }
  return `cid-${Date.now()}-${Math.random().toString(16).slice(2)}`
}
const clientId = createClientId()
const GUEST_PREFIXES = ['Быстрый', 'Тихий', 'Северный', 'Смелый', 'Яркий', 'Лунный']
const GUEST_NAMES = ['Лис', 'Кот', 'Енот', 'Сокол', 'Волк', 'Панда']
function randomGuestName() {
  const p = GUEST_PREFIXES[Math.floor(Math.random() * GUEST_PREFIXES.length)]
  const n = GUEST_NAMES[Math.floor(Math.random() * GUEST_NAMES.length)]
  const suffix = Math.floor(10 + Math.random() * 90)
  return `${p} ${n} #${suffix}`
}
const guestName = randomGuestName()
const displayName = computed(() => {
  const raw = String(auth.username || '').trim()
  return raw || guestName
})
const isGuest = computed(() => !String(auth.username || '').trim())
const usersByClient = ref({})
const chatMessages = ref([])
const chatInput = ref('')

/** Последнее известное состояние ведущего (для подтягивания гостя) */
const latestHostSync = ref(null)

/** Для iframe: последнее применённое время (чтобы не дергать src на каждом play/pause с тем же t) */
const lastEmbedAppliedT = ref(-1)

/** Rutube embed: время и состояние из postMessage API плеера */
const rutubeCurrentTime = ref(0)
const rutubePlaying = ref(false)

let rutubeMessageHandler = null

const provider = computed(() => props.room.provider)
const isDirect = computed(() => Boolean(props.room.stream_url))
const isEmbed = computed(() => Boolean(props.room.embed_url) && !isDirect.value)

const isHost = computed(() => {
  const oid = props.room.owner_id
  if (oid == null) return false
  const uid = auth.userId
  if (uid == null) return false
  return Number(oid) === Number(uid)
})

const roleLabel = computed(() =>
  isHost.value ? 'Вы ведущий — управление синхронизируется с остальными' : 'Синхронизация с ведущим (создателем комнаты)',
)

function wsPath() {
  const p = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${p}//${window.location.host}/ws/room/${props.room.slug}/`
}

function sendEvent(payload) {
  if (ws?.readyState !== WebSocket.OPEN) return
  ws.send(
    JSON.stringify({
      ...payload,
      from: clientId,
      ts: Date.now(),
    }),
  )
}

function sendSync(payload) {
  if (!isHost.value) return
  sendEvent({ type: 'sync', ...payload })
}

function upsertUser(payload) {
  const key = String(payload.from || '')
  if (!key) return
  usersByClient.value = {
    ...usersByClient.value,
    [key]: {
      id: key,
      name: payload.name || 'Гость',
      guest: payload.guest === true,
      host: payload.host === true,
      lastSeen: Date.now(),
    },
  }
}

function removeUser(clientKey) {
  const key = String(clientKey || '')
  if (!key || !usersByClient.value[key]) return
  const next = { ...usersByClient.value }
  delete next[key]
  usersByClient.value = next
}

const roomUsers = computed(() =>
  Object.values(usersByClient.value)
    .filter((u) => Date.now() - Number(u.lastSeen || 0) < PRESENCE_STALE_MS)
    .sort((a, b) => {
      if (a.host !== b.host) return a.host ? -1 : 1
      return String(a.name).localeCompare(String(b.name), 'ru')
    }),
)

function presencePayload(type) {
  return {
    type,
    name: displayName.value,
    guest: isGuest.value,
    host: isHost.value,
  }
}

function sendPresenceHello() {
  sendEvent(presencePayload('presence:hello'))
}

function sendPresenceState() {
  sendEvent(presencePayload('presence:state'))
}

function sendPresencePing() {
  sendEvent(presencePayload('presence:ping'))
}

function sendPresenceBye() {
  sendEvent({ type: 'presence:bye' })
}

function stopPresenceTimers() {
  if (presencePingTimer != null) {
    clearInterval(presencePingTimer)
    presencePingTimer = null
  }
  if (presenceSweepTimer != null) {
    clearInterval(presenceSweepTimer)
    presenceSweepTimer = null
  }
}

function startPresenceTimers() {
  stopPresenceTimers()
  presencePingTimer = setInterval(() => {
    if (connected.value) sendPresencePing()
  }, PRESENCE_PING_MS)
  presenceSweepTimer = setInterval(() => {
    const now = Date.now()
    const next = { ...usersByClient.value }
    let changed = false
    for (const [key, user] of Object.entries(next)) {
      if (now - Number(user.lastSeen || 0) >= PRESENCE_STALE_MS) {
        delete next[key]
        changed = true
      }
    }
    if (changed) usersByClient.value = next
  }, 5000)
}

function pushChatMessage(data) {
  const text = String(data.text || '').trim()
  if (!text) return
  const entry = {
    id: `${data.from || 'unknown'}-${data.ts || Date.now()}`,
    from: String(data.from || ''),
    name: data.name || 'Гость',
    guest: data.guest === true,
    text,
    ts: Number(data.ts || Date.now()),
  }
  chatMessages.value = [...chatMessages.value, entry].slice(-CHAT_HISTORY_LIMIT)
}

function sendChatMessage() {
  const text = String(chatInput.value || '').trim()
  if (!text || !connected.value) return
  sendEvent({
    type: 'chat:message',
    text,
    name: displayName.value,
    guest: isGuest.value,
  })
  chatInput.value = ''
}

function stopHostTick() {
  if (hostTickTimer != null) {
    clearInterval(hostTickTimer)
    hostTickTimer = null
  }
}

function startHostTick() {
  stopHostTick()
  if (!isHost.value) return
  hostTickTimer = setInterval(() => {
    if (!isHost.value) return
    try {
      if (isDirect.value && vjs) {
        sendSync({ action: 'tick', t: vjs.currentTime(), playing: !vjs.paused() })
      } else if (provider.value === 'youtube' && ytPlayer?.getPlayerState) {
        const st = ytPlayer.getPlayerState()
        const playing = st === window.YT.PlayerState.PLAYING
        sendSync({ action: 'tick', t: ytPlayer.getCurrentTime(), playing })
      } else if (provider.value === 'rutube' && iframeEl.value) {
        sendSync({
          action: 'tick',
          t: rutubeCurrentTime.value,
          playing: rutubePlaying.value,
        })
      }
    } catch {
      /* ignore */
    }
  }, HOST_TICK_MS)
}

function updateLatestHostSync(data) {
  const t = typeof data.t === 'number' ? data.t : 0
  const act = data.action
  if (act === 'tick') {
    latestHostSync.value = { t, playing: data.playing === true }
  } else if (act === 'play') {
    latestHostSync.value = { t, playing: true }
  } else if (act === 'pause') {
    latestHostSync.value = { t, playing: false }
  } else if (act === 'seek') {
    const p = data.playing
    latestHostSync.value = {
      t,
      playing: p === true ? true : p === false ? false : latestHostSync.value?.playing ?? true,
    }
  }
}

function guessMime(url) {
  const u = (url || '').toLowerCase()
  if (u.includes('.m3u8')) return 'application/x-mpegURL'
  if (u.includes('.webm')) return 'video/webm'
  return 'video/mp4'
}

function getDirectTime() {
  if (!vjs) return null
  try {
    return vjs.currentTime()
  } catch {
    return null
  }
}

function getYoutubeTime() {
  if (!ytPlayer?.getCurrentTime) return null
  try {
    return ytPlayer.getCurrentTime()
  } catch {
    return null
  }
}

/** Нужно ли выставлять время точно (учитывая допуск) */
function needsTimeSync(targetT) {
  if (typeof targetT !== 'number' || Number.isNaN(targetT)) return true
  if (isDirect.value) {
    const cur = getDirectTime()
    if (cur == null) return true
    return Math.abs(cur - targetT) > SYNC_TOLERANCE_SEC
  }
  if (provider.value === 'youtube') {
    const cur = getYoutubeTime()
    if (cur == null) return true
    return Math.abs(cur - targetT) > SYNC_TOLERANCE_SEC
  }
  return true
}

function setupDirect() {
  if (!directEl.value) return
  const host = isHost.value
  const opts = {
    controls: true,
    fluid: true,
    sources: [{ src: props.room.stream_url, type: guessMime(props.room.stream_url) }],
  }
  if (!host) {
    Object.assign(opts, {
      bigPlayButton: false,
      userActions: { click: false, doubleClick: false, hotkeys: false },
      controlBar: {
        playToggle: false,
        progressControl: false,
        pictureInPictureToggle: false,
      },
    })
  }
  vjs = videojs(directEl.value, opts)
  const emit = (action, extra = {}) => {
    if (!isHost.value || applying.value || !vjs) return
    sendSync({ action, t: vjs.currentTime(), ...extra })
  }
  vjs.on('play', () => emit('play', { playing: true }))
  vjs.on('pause', () => emit('pause', { playing: false }))
  vjs.on('seeked', () => emit('seek', { playing: !vjs.paused() }))
  startHostTick()
}

function loadYouTubeApi() {
  return new Promise((resolve) => {
    if (window.YT?.Player) {
      resolve()
      return
    }
    const tag = document.createElement('script')
    tag.src = 'https://www.youtube.com/iframe_api'
    const first = document.getElementsByTagName('script')[0]
    first.parentNode.insertBefore(tag, first)
    const prev = window.onYouTubeIframeAPIReady
    window.onYouTubeIframeAPIReady = () => {
      prev?.()
      resolve()
    }
  })
}

function styleYoutubeIframeFill() {
  try {
    const ifr = ytPlayer?.getIframe?.()
    if (!ifr) return
    ifr.setAttribute('width', '100%')
    ifr.setAttribute('height', '100%')
    ifr.style.cssText =
      'position:absolute!important;top:0!important;left:0!important;width:100%!important;height:100%!important;border:0;'
  } catch {
    /* ignore */
  }
}

function onYoutubeGuestVolume(v) {
  const n = Math.max(0, Math.min(100, Number(v)))
  ytGuestVolume.value = n
  try {
    ytPlayer?.setVolume?.(n)
  } catch {
    /* ignore */
  }
}

function toggleYoutubeFullscreen() {
  const el = ytWrap.value
  if (!el) return
  if (document.fullscreenElement) {
    document.exitFullscreen?.()
  } else {
    el.requestFullscreen?.() || el.webkitRequestFullscreen?.()
  }
}

function toggleEmbedFullscreen() {
  const el = embedWrap.value
  if (!el) return
  if (document.fullscreenElement) {
    document.exitFullscreen?.()
  } else {
    el.requestFullscreen?.() || el.webkitRequestFullscreen?.()
  }
}

function isRutubeOrigin(origin) {
  try {
    const h = new URL(origin).hostname
    return h === 'rutube.ru' || h.endsWith('.rutube.ru')
  } catch {
    return false
  }
}

/** https://rutube.ru/info/embed/ — управление через postMessage */
function postRutube(type, data = {}) {
  if (provider.value !== 'rutube' || !iframeEl.value?.contentWindow) return
  try {
    iframeEl.value.contentWindow.postMessage(JSON.stringify({ type, data }), '*')
  } catch {
    /* ignore */
  }
}

function parseRutubeMessage(raw) {
  if (raw && typeof raw === 'object' && raw.type) return raw
  if (typeof raw !== 'string') return null
  try {
    return JSON.parse(raw)
  } catch {
    return null
  }
}

function rutubeStateToPlaying(state) {
  const s = String(state ?? '').toLowerCase()
  if (s === 'playing' || s === 'play') return true
  if (s === 'paused' || s === 'pause' || s === 'ended' || s === 'idle') return false
  if (s.includes('buffer') || s.includes('load') || s.includes('ad')) return null
  return null
}

function needsTimeSyncRutube(targetT) {
  if (typeof targetT !== 'number' || Number.isNaN(targetT)) return true
  return Math.abs(rutubeCurrentTime.value - targetT) > SYNC_TOLERANCE_SEC
}

function applyRutubeRemote(data) {
  const t = typeof data.t === 'number' ? data.t : 0
  const act = data.action
  if (act === 'tick') {
    const playing = data.playing === true
    if (needsTimeSyncRutube(t)) postRutube('player:setCurrentTime', { time: t })
    if (playing) postRutube('player:play', {})
    else postRutube('player:pause', {})
    return
  }
  if (act === 'seek') {
    postRutube('player:setCurrentTime', { time: t })
    if (data.playing === false) postRutube('player:pause', {})
    else postRutube('player:play', {})
    return
  }
  if (act === 'play') {
    if (needsTimeSyncRutube(t)) postRutube('player:setCurrentTime', { time: t })
    postRutube('player:play', {})
  }
  if (act === 'pause') {
    if (needsTimeSyncRutube(t)) postRutube('player:setCurrentTime', { time: t })
    postRutube('player:pause', {})
  }
}

function resyncGuestRutubeFromHost() {
  if (isHost.value || applying.value || provider.value !== 'rutube') return
  const s = latestHostSync.value
  if (!s) return
  applying.value = true
  try {
    if (needsTimeSyncRutube(s.t)) postRutube('player:setCurrentTime', { time: s.t })
    if (s.playing) postRutube('player:play', {})
    else postRutube('player:pause', {})
  } finally {
    applying.value = false
  }
}

function onRutubeWindowMessage(event) {
  if (!isRutubeOrigin(event.origin)) return
  const msg = parseRutubeMessage(event.data)
  if (!msg?.type) return

  const d = msg.data && typeof msg.data === 'object' ? msg.data : {}

  if (msg.type === 'player:currentTime' || msg.type === 'player:timeUpdate') {
    const time = Number(d.time ?? d.currentTime ?? d.current ?? d.position)
    if (!Number.isNaN(time)) rutubeCurrentTime.value = time
    return
  }

  if (msg.type === 'player:changeState') {
    const ct = Number(d.currentTime ?? d.time)
    if (!Number.isNaN(ct)) rutubeCurrentTime.value = ct
    const playing = rutubeStateToPlaying(d.state)
    if (playing !== null) rutubePlaying.value = playing
    if (isHost.value && !applying.value && playing !== null) {
      const t = rutubeCurrentTime.value
      if (playing === true) sendSync({ action: 'play', t, playing: true })
      else if (playing === false) sendSync({ action: 'pause', t, playing: false })
    } else if (!isHost.value && !applying.value && playing !== null) {
      setTimeout(() => resyncGuestRutubeFromHost(), 80)
    }
  }
}

function bindRutubeMessages() {
  unbindRutubeMessages()
  if (provider.value !== 'rutube') return
  rutubeMessageHandler = (e) => onRutubeWindowMessage(e)
  window.addEventListener('message', rutubeMessageHandler)
}

function unbindRutubeMessages() {
  if (rutubeMessageHandler) {
    window.removeEventListener('message', rutubeMessageHandler)
    rutubeMessageHandler = null
  }
}

function onRutubeIframeLoad() {
  if (provider.value !== 'rutube') return
  bindRutubeMessages()
  startHostTick()
}

function onEmbedIframeLoad() {
  if (provider.value === 'rutube') onRutubeIframeLoad()
}

/** Гость нажал паузу/плей в YouTube — возвращаем к состоянию ведущего */
function resyncGuestYoutubeFromHost() {
  if (isHost.value || applying.value || !ytPlayer?.getPlayerState) return
  const s = latestHostSync.value
  if (!s) return
  applying.value = true
  try {
    const st = ytPlayer.getPlayerState()
    const localPlaying = st === window.YT.PlayerState.PLAYING
    if (localPlaying !== s.playing) {
      if (needsTimeSync(s.t)) seekYoutube(s.t)
      if (s.playing) playYoutube()
      else pauseYoutube()
    } else if (needsTimeSync(s.t)) {
      seekYoutube(s.t)
    }
  } finally {
    applying.value = false
  }
}

function setupYoutube() {
  loadYouTubeApi().then(() => {
    if (!ytHost.value) return
    const vid = props.room.extra?.video_id
    const hostControls = isHost.value ? 1 : 0
    ytPlayer = new window.YT.Player(ytHost.value, {
      width: '100%',
      height: '100%',
      videoId: vid,
      playerVars: { rel: 0, controls: hostControls, playsinline: 1 },
      events: {
        onReady: () => {
          styleYoutubeIframeFill()
          setTimeout(styleYoutubeIframeFill, 400)
          try {
            if (!isHost.value && ytPlayer?.getVolume) {
              ytGuestVolume.value = ytPlayer.getVolume()
            }
          } catch {
            /* ignore */
          }
          startHostTick()
        },
        onStateChange: (e) => {
          if (isHost.value) {
            if (applying.value || !ytPlayer) return
            const t = ytPlayer.getCurrentTime()
            if (e.data === window.YT.PlayerState.PLAYING) sendSync({ action: 'play', t, playing: true })
            if (e.data === window.YT.PlayerState.PAUSED) sendSync({ action: 'pause', t, playing: false })
            return
          }
          if (applying.value || !ytPlayer) return
          if (
            e.data === window.YT.PlayerState.PLAYING ||
            e.data === window.YT.PlayerState.PAUSED
          ) {
            setTimeout(() => resyncGuestYoutubeFromHost(), 80)
          }
        },
      },
    })
  })
}

function seekYoutube(t) {
  if (!ytPlayer?.seekTo) return
  ytPlayer.seekTo(t, true)
}

function playYoutube() {
  ytPlayer?.playVideo?.()
}

function pauseYoutube() {
  ytPlayer?.pauseVideo?.()
}

function embedSrcAt(seconds) {
  const raw = props.room.embed_url || ''
  try {
    const u = new URL(raw)
    u.searchParams.set('t', String(Math.max(0, Math.floor(seconds))))
    return u.toString()
  } catch {
    const sep = raw.includes('?') ? '&' : '?'
    return `${raw}${sep}t=${Math.max(0, Math.floor(seconds))}`
  }
}

function shouldReloadEmbed(targetT, action) {
  if (action === 'seek') return true
  if (lastEmbedAppliedT.value < 0) return true
  if (typeof targetT !== 'number') return true
  return Math.abs(targetT - lastEmbedAppliedT.value) > SYNC_TOLERANCE_SEC
}

function applyRemote(data) {
  updateLatestHostSync(data)

  const t = typeof data.t === 'number' ? data.t : 0
  const act = data.action
  applying.value = true
  try {
    if (isDirect.value && vjs) {
      if (act === 'tick') {
        const playing = data.playing === true
        if (needsTimeSync(t)) vjs.currentTime(t)
        if (playing && vjs.paused()) vjs.play()
        if (!playing && !vjs.paused()) vjs.pause()
        return
      }
      if (act === 'seek') {
        vjs.currentTime(t)
        if (data.playing === false) vjs.pause()
        else if (data.playing === true) vjs.play()
        return
      }
      if (act === 'play') {
        if (needsTimeSync(t)) vjs.currentTime(t)
        vjs.play()
      }
      if (act === 'pause') {
        if (needsTimeSync(t)) vjs.currentTime(t)
        vjs.pause()
      }
      return
    }
    if (provider.value === 'youtube' && ytPlayer) {
      if (act === 'tick') {
        const playing = data.playing === true
        if (needsTimeSync(t)) seekYoutube(t)
        const st = ytPlayer.getPlayerState()
        const curPlaying = st === window.YT.PlayerState.PLAYING
        if (playing && !curPlaying) playYoutube()
        if (!playing && curPlaying) pauseYoutube()
        return
      }
      if (act === 'seek') {
        seekYoutube(t)
        if (data.playing === false) pauseYoutube()
        else if (data.playing === true) playYoutube()
        return
      }
      if (act === 'play') {
        if (needsTimeSync(t)) seekYoutube(t)
        playYoutube()
      }
      if (act === 'pause') {
        if (needsTimeSync(t)) seekYoutube(t)
        pauseYoutube()
      }
      return
    }
    if (iframeEl.value && provider.value === 'rutube') {
      applyRutubeRemote(data)
      return
    }
    if (iframeEl.value && provider.value === 'vk') {
      if (!shouldReloadEmbed(t, act)) return
      iframeEl.value.src = embedSrcAt(t)
      lastEmbedAppliedT.value = t
    }
  } finally {
    applying.value = false
  }
}

function onSocketMessage(ev) {
  let data
  try {
    data = JSON.parse(ev.data)
  } catch {
    return
  }
  if (!data?.type) return
  if (data.type === 'sync') {
    if (data.from === clientId) return
    applyRemote(data)
    return
  }
  if (data.type === 'presence:hello') {
    upsertUser(data)
    if (data.from !== clientId) sendPresenceState()
    return
  }
  if (data.type === 'presence:state' || data.type === 'presence:ping') {
    upsertUser(data)
    return
  }
  if (data.type === 'presence:bye') {
    removeUser(data.from)
    return
  }
  if (data.type === 'chat:message') {
    pushChatMessage(data)
  }
}

function connectWs() {
  ws = new WebSocket(wsPath())
  ws.onopen = () => {
    connected.value = true
    upsertUser({
      from: clientId,
      name: displayName.value,
      guest: isGuest.value,
      host: isHost.value,
    })
    sendPresenceHello()
    startPresenceTimers()
  }
  ws.onclose = () => {
    connected.value = false
    stopPresenceTimers()
  }
  ws.onmessage = onSocketMessage
}

function disposePlayers() {
  stopHostTick()
  stopPresenceTimers()
  unbindRutubeMessages()
  if (vjs) {
    vjs.dispose()
    vjs = null
  }
  ytPlayer = null
  lastEmbedAppliedT.value = -1
  latestHostSync.value = null
  rutubeCurrentTime.value = 0
  rutubePlaying.value = false
}

onMounted(async () => {
  connectWs()
  await nextTick()
  if (isDirect.value) setupDirect()
  if (provider.value === 'youtube') setupYoutube()
  if (provider.value === 'rutube') {
    setTimeout(() => {
      if (!rutubeMessageHandler) onRutubeIframeLoad()
    }, 800)
  }
})

onBeforeUnmount(() => {
  sendPresenceBye()
  ws?.close()
  disposePlayers()
})

watch(
  () => props.room.slug,
  () => {
    ws?.close()
    disposePlayers()
    lastEmbedAppliedT.value = -1
    usersByClient.value = {}
    chatMessages.value = []
    connectWs()
    nextTick().then(() => {
      if (isDirect.value) setupDirect()
      if (provider.value === 'youtube') setupYoutube()
    })
  },
)
</script>

<template>
  <div class="player-wrap">
    <div class="meta">
      <span class="pill" :class="{ ok: connected }">
        {{ connected ? 'Канал синхронизации: онлайн' : 'Канал синхронизации: нет соединения' }}
      </span>
      <span class="pill role">{{ roleLabel }}</span>
      <span class="provider">{{ room.provider }}</span>
    </div>

    <video v-if="isDirect" ref="directEl" class="video-js vjs-default-skin" playsinline />

    <div v-else-if="provider === 'youtube'" class="youtube-block">
      <div ref="ytWrap" class="yt-wrap">
        <div ref="ytHost" class="yt-host-inner" />
      </div>
      <div v-if="!isHost" class="guest-media-tools">
        <span class="tool-label">Громкость</span>
        <v-slider
          class="vol-slider"
          :model-value="ytGuestVolume"
          hide-details
          density="compact"
          color="primary"
          @update:model-value="onYoutubeGuestVolume"
        />
        <v-btn size="small" variant="tonal" color="primary" @click="toggleYoutubeFullscreen">
          На весь экран
        </v-btn>
      </div>
    </div>

    <div v-else-if="isEmbed" class="embed-block">
      <div ref="embedWrap" class="embed-wrap">
        <iframe
          ref="iframeEl"
          class="embed-frame"
          :src="room.embed_url"
          allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; fullscreen"
          allowfullscreen
          @load="onEmbedIframeLoad"
        />
      </div>
      <div v-if="!isHost" class="guest-media-tools">
        <v-btn size="small" variant="tonal" color="primary" @click="toggleEmbedFullscreen">
          На весь экран
        </v-btn>
      </div>
    </div>

    <div v-else class="empty">Нет источника воспроизведения</div>

    <p v-if="provider === 'rutube'" class="hint">
      Rutube: синхронизация через postMessage API плеера (play/pause/время). Ведущий рассылает также периодические тики.
    </p>
    <p v-else-if="provider === 'vk'" class="hint">
      VK: синхронизация через перезагрузку встраивания при сильном расхождении (допуск {{ SYNC_TOLERANCE_SEC }} с).
    </p>

    <section class="room-social">
      <div class="users-panel">
        <h3>В комнате ({{ roomUsers.length }})</h3>
        <ul class="users-list">
          <li v-for="u in roomUsers" :key="u.id">
            <span class="user-name">{{ u.name }}</span>
            <span v-if="u.host" class="user-badge host">ведущий</span>
            <span v-else-if="u.guest" class="user-badge guest">гость</span>
          </li>
        </ul>
      </div>

      <div class="chat-panel">
        <h3>Чат комнаты</h3>
        <div class="chat-list">
          <div v-for="m in chatMessages" :key="m.id" class="chat-item">
            <span class="chat-author" :class="{ me: m.from === clientId }">
              {{ m.from === clientId ? 'Вы' : m.name }}
            </span>
            <span class="chat-text">{{ m.text }}</span>
          </div>
          <div v-if="chatMessages.length === 0" class="chat-empty">Пока нет сообщений</div>
        </div>
        <div class="chat-send">
          <input
            v-model="chatInput"
            class="chat-input"
            type="text"
            maxlength="400"
            placeholder="Введите сообщение..."
            @keydown.enter.prevent="sendChatMessage"
          />
          <button class="chat-btn" type="button" :disabled="!connected || !chatInput.trim()" @click="sendChatMessage">
            Отправить
          </button>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.player-wrap {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.meta {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
}
.pill {
  font-size: 13px;
  padding: 4px 10px;
  border-radius: 999px;
  background: #2a2a35;
  color: #ccc;
}
.pill.ok {
  background: #1b3d2a;
  color: #8fffc1;
}
.pill.role {
  max-width: 100%;
  white-space: normal;
  line-height: 1.4;
  background: #252532;
  color: #c4c4e0;
}
.provider {
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-size: 12px;
  color: #888;
}
.youtube-block,
.embed-block {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
}
.guest-media-tools {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  padding: 4px 0 8px;
}
.tool-label {
  font-size: 13px;
  color: #aaa;
  flex: 0 0 auto;
}
.vol-slider {
  flex: 1;
  min-width: 160px;
  max-width: 320px;
}
/* Контейнер 16:9; плеер YouTube заполняет его полностью */
.yt-wrap {
  position: relative;
  width: 100%;
  aspect-ratio: 16 / 9;
  border-radius: 12px;
  overflow: hidden;
  background: #000;
}
.yt-host-inner {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  min-height: 0;
}
.embed-wrap {
  position: relative;
  width: 100%;
  aspect-ratio: 16 / 9;
  border-radius: 12px;
  overflow: hidden;
  background: #000;
}
.embed-wrap .embed-frame {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  border: 0;
  display: block;
}
.empty {
  padding: 24px;
  color: #888;
}
.hint {
  font-size: 13px;
  color: #9a9aaa;
  line-height: 1.5;
  max-width: 720px;
}
.room-social {
  display: grid;
  grid-template-columns: minmax(220px, 280px) 1fr;
  gap: 12px;
  margin-top: 4px;
}
.users-panel,
.chat-panel {
  border: 1px solid #2c2c39;
  border-radius: 12px;
  padding: 12px;
  background: #181820;
}
.users-panel h3,
.chat-panel h3 {
  margin: 0 0 10px;
  font-size: 14px;
  color: #d7d7e7;
}
.users-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.users-list li {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 22px;
}
.user-name {
  color: #e6e6f2;
  font-size: 14px;
}
.user-badge {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  border-radius: 999px;
  padding: 2px 8px;
}
.user-badge.host {
  background: #243742;
  color: #84d7ff;
}
.user-badge.guest {
  background: #2f2a39;
  color: #d0b8ff;
}
.chat-list {
  border: 1px solid #2b2b38;
  border-radius: 10px;
  padding: 10px;
  min-height: 150px;
  max-height: 260px;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.chat-item {
  display: flex;
  gap: 8px;
  align-items: baseline;
  word-break: break-word;
}
.chat-author {
  color: #9cc3ff;
  font-size: 13px;
  font-weight: 600;
}
.chat-author.me {
  color: #8fffc1;
}
.chat-text {
  color: #e7e7ef;
  font-size: 14px;
}
.chat-empty {
  color: #8e8ea5;
  font-size: 13px;
}
.chat-send {
  margin-top: 10px;
  display: flex;
  gap: 8px;
}
.chat-input {
  flex: 1;
  border: 1px solid #363649;
  border-radius: 8px;
  padding: 8px 10px;
  background: #111119;
  color: #ececff;
  outline: none;
}
.chat-input:focus {
  border-color: #5f72ff;
}
.chat-btn {
  border: 1px solid #4f67ff;
  background: #384de3;
  color: #fff;
  border-radius: 8px;
  padding: 8px 12px;
  cursor: pointer;
}
.chat-btn:disabled {
  opacity: 0.45;
  cursor: default;
}
@media (max-width: 960px) {
  .room-social {
    grid-template-columns: 1fr;
  }
}
</style>
