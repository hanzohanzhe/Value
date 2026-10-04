# Prompt 79 — Capability-led Study composer

Execute after Prompt 78. Read its live workspace/draft-resolution API, current
Studies page, module cards, parameter registry and Prompt 26 accessibility
requirements. Act as a product designer, frontend engineer and power-system
study-design reviewer. Keep the shipped UI in English and update bilingual
documentation later in Prompt 84.

## Objective

Replace the fixed seven-dropdown form with a capability-led composer that lets a
non-programmer create a valid Study while preserving advanced control. The form
must describe the scientific question first and derive compatible choices from
the server-owned registry.

## Study flow

Provide a progressive five-step composer:

1. **Study identity:** name, years, data pack and purpose.
2. **System domain:** single node, reference DC network or experimental AC
   feasibility. Explain that AC feasibility checks a declared active schedule
   and is not AC OPF.
3. **Optional domains:** hydrology and transmission expansion, each with
   maturity, required capabilities and an explicit selection. Never enable an
   extension merely because its files exist.
4. **Model chain:** show only compatible PSM/CEM modules and optional slots,
   including storage-cost applicability and `network_expansion`.
5. **Inputs and assumptions:** show conditional data readiness, effective base
   and extension parameters, runtime outputs and the final graph preview.

Offer a Basic view with recommended compatible defaults and an Advanced view
with exact module/extension IDs and parameter sources. Defaults may fill a
choice only after the user chooses a domain; they must be visible and saved.

## Scientific and usability rules

- Render labels/descriptions from manifests and generated metadata, not string
  matching or module-ID conditionals.
- Show `ready`, `experimental` and `not evaluated` separately. Experimental
  selection requires a concise, versioned acknowledgement stored in the Study.
- Disable, rather than hide, scientifically relevant incompatible choices and
  show the exact missing capability, data role, solver or licence reason.
- Do not describe local AC feasibility as optimization or the transmission
  reference lifecycle as a recommended national plan.
- Present interconnectors as boundary imports, never internal branches.
- Changing data, module, extension, years, scientific parameters or maturity
  acknowledgement creates a new revision. Editing a display name alone does not.
- The final Review step shows module IDs/versions, extensions, data-pack revision,
  conditional roles, parameters, information structure and graph SHA-256.

## Tests and acceptance

Rendered/component and browser tests must cover successful single-node, DC,
hydrology and DC-plus-expansion compositions; AC experimental acknowledgement;
missing data; missing solver; incompatible choices; back/forward navigation;
reload of a saved revision; keyboard-only operation; mobile layout; and error
recovery without losing entered values.

The submitted JSON must exactly match the Review screen and Prompt 78 preview.
The existing single-node default must retain its frozen graph hash. Stop if the
frontend needs its own compatibility algorithm or silently modifies a user's
selection to make preflight pass.

