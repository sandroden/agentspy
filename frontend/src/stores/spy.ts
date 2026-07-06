import { defineStore } from 'pinia'
import { ref } from 'vue'

interface Session {
  id: string
  name: string
  // TODO: expand in F4b
}

interface Event {
  id: number
  timestamp: number
  type: string
  // TODO: expand in F4b
}

export const useSpyStore = defineStore('spy', () => {
  const sessions = ref<Session[]>([])
  const events = ref<Event[]>([])
  const cursor = ref(-1)
  const live = ref(true)

  // TODO: implement actions in F4b

  return {
    sessions,
    events,
    cursor,
    live,
  }
})
