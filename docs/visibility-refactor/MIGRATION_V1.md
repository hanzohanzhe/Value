# v1 project and historical-run migration

`gridform.project/v1` remains supported. A runnable project must contain
`data_pack_id`, `start_year`, `end_year`, all five module slots, `parameters` and
`runtime_options`. The example in `examples/scheme-c-final.scenario.json` is the
canonical shape.

Prototype scenario files that used generic `engines`, `profiles` or a network
field are not executed implicitly. Create a new research project, choose an
installed data pack and map each old choice to a registered module ID. Unknown
choices fail validation instead of falling back to Scheme C.

Historical run directories are immutable. GridForm never upgrades their status,
rewrites their result schema or regenerates their provenance. Only runs marked
`gridform-annual-orchestrator/v2` appear in the normal Run centre. Older bundles
remain available on disk for explicit reference comparison and audit.
