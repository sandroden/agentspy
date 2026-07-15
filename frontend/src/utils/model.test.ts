import { describe, it, expect } from 'vitest'
import { modelFamily, modelColor, abbreviateModel } from './model'

describe('modelFamily', () => {
  it('recognizes the known families', () => {
    expect(modelFamily('claude-opus-4-8')).toBe('opus')
    expect(modelFamily('claude-sonnet-5')).toBe('sonnet')
    expect(modelFamily('claude-haiku-4-5')).toBe('haiku')
    expect(modelFamily('claude-fable-5')).toBe('fable')
  })

  it('recognizes GLM ids with and without vendor prefix', () => {
    expect(modelFamily('z-ai/glm-5.2')).toBe('glm')
    expect(modelFamily('glm-4.7-flash')).toBe('glm')
  })

  it('falls back to unknown for null and unrecognized strings', () => {
    expect(modelFamily(null)).toBe('unknown')
    expect(modelFamily(undefined)).toBe('unknown')
    expect(modelFamily('gpt-4o')).toBe('unknown')
    expect(modelFamily('claude-mythos-5')).toBe('unknown')
  })
})

describe('modelColor', () => {
  it('assigns a distinct color per known family', () => {
    const colors = [
      modelColor('claude-opus-4-8'),
      modelColor('claude-sonnet-5'),
      modelColor('claude-haiku-4-5'),
      modelColor('claude-fable-5'),
    ]
    expect(new Set(colors).size).toBe(4)
  })

  it('unknown families fall back to the global accent token', () => {
    expect(modelColor('gpt-4o')).toBe('var(--accent)')
    expect(modelColor(null)).toBe('var(--accent)')
  })
})

describe('abbreviateModel', () => {
  it('collapses to family-major.minor', () => {
    expect(abbreviateModel('claude-opus-4-8')).toBe('opus-4.8')
    expect(abbreviateModel('claude-sonnet-4-5')).toBe('sonnet-4.5')
  })

  it('drops the minor when absent', () => {
    expect(abbreviateModel('claude-sonnet-5')).toBe('sonnet-5')
    expect(abbreviateModel('claude-fable-5')).toBe('fable-5')
  })

  it('handles null and long unrecognized ids', () => {
    expect(abbreviateModel(null)).toBe('—')
    expect(abbreviateModel('a-very-long-unknown-model-id')).toBe('a-very-long-un…')
    expect(abbreviateModel('short')).toBe('short')
  })

  it('drops the vendor prefix from gateway ids', () => {
    expect(abbreviateModel('z-ai/glm-5.2')).toBe('glm-5.2')
    expect(abbreviateModel('glm-4.7-flash')).toBe('glm-4.7-flash')
  })
})
