/** Light/dark theme toggle, persisted in localStorage, applied as a
 * `data-theme` attribute on <html> (see App.vue :root / [data-theme="dark"]). */
import { ref } from 'vue'

const STORAGE_KEY = 'agentspy.theme'

export type Theme = 'light' | 'dark'

function readStored(): Theme {
  return localStorage.getItem(STORAGE_KEY) === 'dark' ? 'dark' : 'light'
}

const theme = ref<Theme>(readStored())

function apply(t: Theme) {
  document.documentElement.dataset.theme = t
}

export function useTheme() {
  function setTheme(t: Theme) {
    theme.value = t
    localStorage.setItem(STORAGE_KEY, t)
    apply(t)
  }

  function init() {
    apply(theme.value)
  }

  return { theme, setTheme, init }
}
