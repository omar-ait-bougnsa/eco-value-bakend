import { describe, expect, it } from 'vitest'
import { rangeError } from './NumberField'

// The bounds come from the server (GET /limits); the wording follows its messages so a field reads the same before and after it answers.
describe('rangeError', () => {
  it('accepts a number inside its bounds, and an empty optional field', () => {
    expect(rangeError(0.16, { min: 0, max: 3 })).toBeNull()
    expect(rangeError(0, { min: 0, max: 3 })).toBeNull()
    expect(rangeError(null, { min: 0, max: 3 })).toBeNull()
  })
  it('names the bounds and the unit', () => {
    expect(rangeError(760, { min: 0, max: 3, unit: 't/t' })).toBe('must be between 0 and 3 t/t')
    expect(rangeError(-1, { min: 0, max: 10, unit: 't CO₂/t' })).toBe('must be between 0 and 10 t CO₂/t')
    expect(rangeError(900, { min: 0, max: 200, unit: '%' })).toBe('must be between 0 and 200 %')
  })
  it('refuses the lower bound itself when the value must be above it', () => {
    expect(rangeError(0, { min: 0, max: 5, above: true, unit: 't/ha' })).toBe('must be above 0 and at most 5 t/ha')
    expect(rangeError(0.162, { min: 0, max: 5, above: true })).toBeNull()
  })
  it('refuses what is not a finite number, and a missing required value', () => {
    expect(rangeError(NaN, { min: 0 })).toBe('must be a number')
    expect(rangeError(Infinity, { max: 3 })).toBe('must be a number')
    expect(rangeError(null, { required: true })).toBe('is required')
  })
})
