import React from "react"
import Select from "react-select"

/**
 * A labelled react-select that actually shows its selection.
 *
 * react-select needs the whole {value,label} option as `value`, not a bare
 * string. Every one of the ten selects on the old page passed the string and
 * then faked the display through `placeholder`, so the control never looked
 * selected. Resolving the option here fixes it once, the same way
 * CapitalMarkets/FrequencySelect does -- but the options arrive as a prop,
 * because this page has a different list per metric rather than one global set.
 */
const OptionSelect = ({ id, label, options, value, onChange }) => (
  <div className="d-inline-block me-3 mb-3 mb-lg-0 text-start">
    <label className="form-label me-2" htmlFor={id}>
      {label}
    </label>
    <Select
      inputId={id}
      instanceId={id}
      options={options}
      value={options.find((option) => option.value === value) ?? null}
      onChange={(option) => onChange(option.value)}
      className="dropdown bootstrap-select"
      classNamePrefix="selectpicker"
    />
  </div>
)

export default OptionSelect
