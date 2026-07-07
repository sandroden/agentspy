import { onBeforeUnmount, onMounted, ref, type Ref } from 'vue'

/**
 * Osserva la larghezza di `el` con ResizeObserver e la restituisce reattiva.
 * Usata dai grafici SVG per ricalcolare il viewBox su resize mantenendo
 * width:100%. Il componente crea e possiede la template ref (`const el =
 * ref()` + `ref="el"`) e la passa qui, così Volar la riconosce come usata.
 */
export function useElementWidth(el: Ref<HTMLElement | null>, fallback = 640): Ref<number> {
  const width = ref(fallback)
  let observer: ResizeObserver | null = null

  onMounted(() => {
    if (!el.value) return
    observer = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width
      if (w && w > 0) width.value = w
    })
    observer.observe(el.value)
    const initial = el.value.clientWidth
    if (initial > 0) width.value = initial
  })

  onBeforeUnmount(() => {
    observer?.disconnect()
    observer = null
  })

  return width
}
