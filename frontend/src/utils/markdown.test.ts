import { describe, expect, it } from 'vitest'
import { renderMarkdown, stripLineGutter } from './markdown'

describe('renderMarkdown', () => {
  it('renders headings and lists', () => {
    const html = renderMarkdown('# Title\n\n- one\n- two\n')
    expect(html).toContain('<h1>Title</h1>')
    expect(html).toContain('<li>one</li>')
  })

  it('escapes raw HTML instead of interpreting it', () => {
    // the markers injected by Claude Code must stay visible, and no injection
    const html = renderMarkdown('<system-reminder>hi</system-reminder>')
    expect(html).toContain('&lt;system-reminder&gt;')
    expect(html).not.toContain('<script')
    expect(renderMarkdown('<script>alert(1)</script>')).not.toContain('<script>')
  })
})

describe('stripLineGutter', () => {
  it('removes the Read line numbers', () => {
    expect(stripLineGutter('1\t# Title\n2\ttext\n')).toBe('# Title\ntext\n')
  })

  it('leaves alone text that is not numbered', () => {
    const text = '# Title\n\n1969 was a year\nnormal text\n'
    expect(stripLineGutter(text)).toBe(text)
  })

  it('is a no-op on empty text', () => {
    expect(stripLineGutter('')).toBe('')
  })
})
