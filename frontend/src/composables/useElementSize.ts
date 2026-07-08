import { onBeforeUnmount, onMounted, ref, type Ref } from 'vue'

/**
 * Observes `el`'s width with ResizeObserver and returns it reactively.
 * Used by SVG charts to recompute the viewBox on resize while keeping
 * width:100%. The component creates and owns the template ref (`const el =
 * ref()` + `ref="el"`) and passes it here, so Volar recognizes it as used.
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
