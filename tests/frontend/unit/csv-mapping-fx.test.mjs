import assert from "node:assert/strict";
import test from "node:test";
import { EMPTY_FX, acceptsEur, fxCaption, fxErrors, fxRequest, sourceUnits } from "../../../app/features/data/csvMappingFx.ts";

// F-P05A-1 (designer ruling 2026-10-06): currency and EUR->GBP rate of a price-column mapping.
const price = {
  role: "market.belgium.price", columns: [{ target: "value", target_unit: "GBP/MWh" }], single_value: true, fx_required_for: ["EUR/MWh"],
  conversion_pairs: [{ source_unit: "EUR/MWh", target_unit: "GBP/MWh", requires_fx: true }, { source_unit: "GBP/MWh", target_unit: "GBP/MWh" }],
};

test("only a price role offers EUR, and each currency lists its own source units", () => {
  assert.equal(acceptsEur(price), true);
  assert.equal(acceptsEur({ ...price, fx_required_for: undefined }), false);
  assert.deepEqual(sourceUnits(price, "GBP/MWh", "GBP"), ["GBP/MWh"]);
  assert.deepEqual(sourceUnits(price, "GBP/MWh", "EUR"), ["EUR/MWh"]);
});

test("GBP needs no rate; EUR needs a positive 4-decimal rate, a basis and a 1990-2100 price year", () => {
  assert.deepEqual(fxErrors(EMPTY_FX), {});
  assert.equal(fxRequest(EMPTY_FX), null);
  const empty = fxErrors({ ...EMPTY_FX, currency: "EUR" });
  assert.deepEqual(Object.keys(empty).sort(), ["eurPerGbp", "fxBasis", "priceYear"]);
  for (const message of Object.values(empty)) assert.match(message, /^GF_MAPPING_FX/);
  for (const rate of ["0", "-1", "1.12345", "abc", ""]) assert.ok(fxErrors({ ...EMPTY_FX, currency: "EUR", eurPerGbp: rate, fxBasis: "fixed rate", priceYear: "2022" }).eurPerGbp, rate);
  for (const year of ["1989", "2101", "22", "2022.5"]) assert.ok(fxErrors({ ...EMPTY_FX, currency: "EUR", eurPerGbp: "1.1", fxBasis: "fixed rate", priceYear: year }).priceYear, year);
  assert.ok(fxErrors({ ...EMPTY_FX, currency: "EUR", eurPerGbp: "1.1", fxBasis: "guess", priceYear: "2022" }).fxBasis);
  const draft = { currency: "EUR", eurPerGbp: "1.1628", fxBasis: "annual average", priceYear: "2022" };
  assert.deepEqual(fxErrors(draft), {});
  assert.deepEqual(fxRequest(draft), { eur_per_gbp: 1.1628, fx_basis: "annual average", price_year: 2022 });
});

test("the converted column states the rate, basis and year", () => {
  assert.equal(fxCaption({ eur_per_gbp: 1.1628, fx_basis: "annual average", price_year: 2022 }), "converted at 1.1628 EUR/GBP (annual average, 2022)");
});
