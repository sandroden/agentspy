import type { InjectionKey, Ref } from 'vue'

/** Flag "vista compatta" del DetailPanel, fornito ai discendenti (ContentBlock
 *  → SystemReminderText) per collassare le sezioni <system-reminder>. */
export const compactViewKey: InjectionKey<Ref<boolean>> = Symbol('compactView')

/** cwd della sessione dell'evento selezionato, fornito ai discendenti del
 *  DetailPanel (JsonTree, ContentBlock, MessageBlock, SystemReminderText) per
 *  mostrare i path dei file relativi invece che assoluti. */
export const cwdKey: InjectionKey<Ref<string | null | undefined>> = Symbol('cwd')
