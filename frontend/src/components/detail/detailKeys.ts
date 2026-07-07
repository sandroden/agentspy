import type { InjectionKey, Ref } from 'vue'

/** Flag "vista compatta" del DetailPanel, fornito ai discendenti (ContentBlock
 *  → SystemReminderText) per collassare le sezioni <system-reminder>. */
export const compactViewKey: InjectionKey<Ref<boolean>> = Symbol('compactView')
