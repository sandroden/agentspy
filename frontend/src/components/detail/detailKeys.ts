import type { InjectionKey, Ref } from 'vue'

/** DetailPanel's "compact view" flag, provided to the descendants (ContentBlock
 *  → SystemReminderText) to collapse the <system-reminder> sections. */
export const compactViewKey: InjectionKey<Ref<boolean>> = Symbol('compactView')

/** cwd of the selected event's session, provided to the DetailPanel's
 *  descendants (JsonTree, ContentBlock, MessageBlock, SystemReminderText) to
 *  show file paths as relative instead of absolute. */
export const cwdKey: InjectionKey<Ref<string | null | undefined>> = Symbol('cwd')
