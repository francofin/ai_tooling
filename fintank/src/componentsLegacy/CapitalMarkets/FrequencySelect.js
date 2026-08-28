import React from "react";
import Select from "react-select";
import { frequencies } from "@utils/capitalMarkets/chartOptions";

/**
 * react-select needs the whole {value,label} option as `value`, not a bare
 * string. The old EquityCharts passed the string, so nothing ever looked
 * selected and each of the 20 dropdowns pushed the current choice through
 * `placeholder` to fake it. Resolving the option here fixes it once.
 */
const FrequencySelect = ({ id, value, onChange }) => (
  <div className="text-center">
    <label className="form-label me-2" htmlFor={id}>
      Frequency
    </label>
    <Select
      inputId={id}
      instanceId={id}
      options={frequencies}
      value={frequencies.find((option) => option.value === value) ?? null}
      className="dropdown bootstrap-select me-3 mb-3 mb-lg-0"
      classNamePrefix="selectpicker"
      onChange={(option) => onChange(option.value)}
    />
  </div>
);

export default FrequencySelect;
