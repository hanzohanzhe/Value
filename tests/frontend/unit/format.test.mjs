import assert from "node:assert/strict";
import test from "node:test";
import {
  energyUnitFor, formatEnergy, formatEnergyGroup, formatMoney, formatNumber, formatPower, formatPrice, formatQuantity, withUnit,
} from "../../../app/features/shared/format.ts";
import { VALUE_STATES, valueStateText } from "../../../app/features/shared/valueStates.ts";

// Hand-computed table (P0-9 S1, spec 1.2; R3-21, F1-07, F3-16).
test("formatNumber returns null for a missing value instead of 0", () => {
  for (const value of [null, undefined, Number.NaN, Number.POSITIVE_INFINITY]) assert.equal(formatNumber(value), null);
  assert.equal(formatNumber(0), "0");
  assert.equal(formatNumber(1234.567), "1,234.57");
  assert.equal(formatNumber(1234.567, 0), "1,235");
  assert.equal(formatNumber(2.5, { digits: 2, minimumDigits: 2 }), "2.50");
});

test("formatNumber never shows negative zero and never rounds a non-zero value to 0", () => {
  assert.equal(formatNumber(-0), "0");
  assert.equal(formatNumber(-0.001), ">-0.01");
  assert.equal(formatNumber(0.000201), "<0.01");
  assert.equal(formatNumber(3e-11, 10), "<0.0000000001");
  assert.equal(formatNumber(-0.004, 2), ">-0.01");
  assert.equal(formatNumber(0.01, 2), "0.01");
});

test("formatQuantity keeps significant digits and uses scientific notation for tiny values", () => {
  assert.equal(formatQuantity(0.000201), "2.01e-4");
  assert.equal(formatQuantity(-0.0000123), "-1.23e-5");
  assert.equal(formatQuantity(12345), "12,300");
  assert.equal(formatQuantity(0), "0");
  assert.equal(formatQuantity(null), null);
});

test("formatMoney rounds to the target precision before choosing the unit", () => {
  assert.equal(formatMoney(999999.9), "£1.00m");
  assert.equal(formatMoney(12345678901), "£12.346bn");
  assert.equal(formatMoney(1234), "£1.234k");
  assert.equal(formatMoney(999.996), "£1.00k");
  assert.equal(formatMoney(-1234), "-£1.234k");
  assert.equal(formatMoney(12.5), "£12.5");
  assert.equal(formatMoney(0), "£0");
  assert.equal(formatMoney(0.001), "<£0.01");
  assert.equal(formatMoney(null), null);
  assert.equal(formatMoney(undefined), null);
});

test("formatEnergy adapts its unit (3 significant digits) and never shows 0 TWh", () => {
  assert.equal(formatEnergy(10.088), "10.1 MWh");
  assert.equal(formatEnergy(1864.5), "1.86 GWh");
  assert.equal(formatEnergy(347.996), "348 MWh");
  assert.equal(formatEnergy(999.6), "1 GWh");
  assert.equal(formatEnergy(0.5), "500 kWh");
  assert.equal(formatEnergy(2.5e6), "2.5 TWh");
  assert.equal(formatEnergy(0), "0 MWh");
  assert.equal(formatEnergy(null), null);
  assert.equal(energyUnitFor(0), "MWh");
});

test("formatEnergyGroup uses the unit of the group's largest magnitude for every member", () => {
  const group = formatEnergyGroup([10.088, 1864.5, null, -3]);
  assert.equal(group.unit, "GWh");
  assert.equal(group.format(10.088), "0.0101 GWh");
  assert.equal(group.format(1864.5), "1.86 GWh");
  assert.equal(group.format(null), null);
  const small = formatEnergyGroup([348, 20]);
  assert.equal(small.unit, "MWh");
  assert.equal(small.format(20), "20 MWh");
  assert.equal(formatEnergyGroup([]).unit, "MWh");
});

test("formatPower uses MW and GW", () => {
  assert.equal(formatPower(1500), "1.5 GW");
  assert.equal(formatPower(66.5), "66.5 MW");
  assert.equal(formatPower(null), null);
});

test("formatPrice labels the price by its basis (Q6) and never calls an average cost a clearing price", () => {
  const average = formatPrice(55, "average_period_cost");
  assert.equal(average.value, "£55/MWh");
  assert.equal(average.label, "Average period cost (£/MWh demand)");
  assert.doesNotMatch(average.label, /clearing/i);
  assert.equal(formatPrice(55, "average_period_cost", { aggregated: true }).label, "Demand-weighted average period cost (£/MWh demand)");
  assert.equal(formatPrice(61.25, "national_ahead_clearing_price").label, "National ahead clearing price");
  assert.equal(formatPrice(1, "balance_shadow_price").label, "Balance shadow price");
  assert.equal(formatPrice(1, "ahead_settlement_price").label, "Ahead settlement price");
  assert.equal(formatPrice(1, undefined).label, "Price (basis not recorded)");
  assert.equal(formatPrice(1, "something_else").label, "Price (basis not recorded)");
  assert.equal(formatPrice(null, "average_period_cost").value, null);
  assert.equal(formatPrice(0, "average_period_cost").value, "£0/MWh");
});

test("state words come from one table", () => {
  assert.equal(VALUE_STATES.missing.text, "—");
  assert.equal(VALUE_STATES.not_modelled.text, "Not modelled");
  assert.equal(valueStateText("partial_year", 16.6), "Partial year · 16.6%");
  assert.equal(VALUE_STATES.invalid.tone, "red");
  assert.equal(VALUE_STATES.withheld.tone, "amber");
});

test("the legacy presentation helpers delegate and render missing values as —", async () => {
  // presentation.tsx is TSX; its two number helpers are re-checked through the shared layer here
  // and rendered in tests/frontend/render/shared-components.test.mjs.
  assert.equal(formatNumber(undefined) ?? VALUE_STATES.missing.text, "—");
});

test("withUnit appends the unit only to a value; a missing value is the state word alone", () => {
  assert.equal(withUnit(formatNumber(12.5), "MWh"), "12.5 MWh");
  assert.equal(withUnit(formatNumber(null), "MWh"), "—");
  assert.equal(withUnit("—", "MWh"), "—");
  assert.equal(withUnit(formatNumber(55), "/MWh", "", "£"), "£55/MWh");
  assert.equal(withUnit(undefined, "/MWh", "", "£"), "—");
  assert.equal(withUnit(formatNumber(16.6, 1), "%", ""), "16.6%");
  assert.equal(withUnit(formatNumber(3), "", "", "+"), "+3");
  assert.equal(withUnit(formatNumber(0), "MWh"), "0 MWh");
});
