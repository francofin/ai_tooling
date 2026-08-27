import meta from '@data/indicatorMeta.json'

/**
 * The instance list <-> API spec string, and the client-side validation that
 * makes a 400 from the backend normally unreachable.
 *
 * Indicator state is a list of *instances*, not a map keyed by name: plotting
 * SMA(50) against SMA(200) is the point of the old dual-period control, and a
 * name-keyed map would silently hold only one of them.
 */

/** 'sma' + existing -> 'sma#2'. Ids are stable React keys, not API tokens. */
export const makeInstanceId = (name, existing = []) => {
  const used = existing
    .filter((instance) => instance.name === name)
    .map((instance) => Number(instance.id.split('#')[1]) || 0)
  return `${name}#${used.length ? Math.max(...used) + 1 : 1}`
}

/** A fresh instance with every parameter at its metadata default. */
export const makeInstance = (name, existing = []) => ({
  id: makeInstanceId(name, existing),
  name,
  params: Object.fromEntries(meta[name].params.map((param) => [param.key, param.default])),
})

/**
 * Instances -> 'macd:12:26:9,sma:50'.
 *
 * Two things this is easy to get wrong: the meta key IS the API token (note
 * `stddev`, which the old page called `standardDeviation`), and a zero-param
 * indicator emits a bare `adl` with no trailing colon. `params` order is
 * positional, so macd serializes fast:slow:signal in `params` order.
 */
export const serializeSpec = (instances) =>
  instances
    .map(({ name, params }) => [name, ...meta[name].params.map((param) => params[param.key])].join(':'))
    .join(',')

/** 'macd:12:26:9,sma:50' -> instances. Unknown or malformed tokens are dropped
 *  rather than thrown: this parses a URL a user can hand-edit. */
export const deserializeSpec = (raw) => {
  if (!raw) return []
  return raw.split(',').reduce((instances, token) => {
    if (instances.length >= MAX_INDICATORS) return instances
    const [name, ...values] = token.trim().split(':')
    const entry = meta[name]
    if (!entry || values.length !== entry.params.length) return instances
    const numbers = values.map(Number)
    if (numbers.some((value) => !Number.isInteger(value))) return instances
    const instance = {
      id: makeInstanceId(name, instances),
      name,
      params: Object.fromEntries(entry.params.map((param, index) => [param.key, numbers[index]])),
    }
    if (validateInstance(instance)) return instances
    return [...instances, instance]
  }, [])
}

/**
 * Per-instance validation against the metadata bounds and `constraints`.
 * Returns a map of paramKey -> message, or null when the instance is valid.
 * The rail runs this before serializing, so the backend's 400 branch is
 * normally unreachable and the user sees the error on the offending input.
 */
export const validateInstance = ({ name, params }) => {
  const entry = meta[name]
  const errors = {}

  entry.params.forEach((param) => {
    const value = params[param.key]
    if (!Number.isInteger(value)) {
      errors[param.key] = 'Whole numbers only'
    } else if (value < param.min || value > param.max) {
      errors[param.key] = `Between ${param.min} and ${param.max}`
    }
  })

  if (Object.keys(errors).length === 0) {
    ;(entry.constraints ?? []).forEach(({ op, left, right, message }) => {
      if (op === 'lt' && !(params[left] < params[right])) errors[left] = message
    })
  }

  return Object.keys(errors).length ? errors : null
}

/** Max tickers on the rail, and max indicator instances the API accepts. */
export const MAX_SYMBOLS = 5
export const MAX_INDICATORS = 12

export { meta as indicatorMeta }
