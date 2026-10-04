# Synthetic zonal-network data template

This CC0 fixture demonstrates the eight required roles of
`value.zonal-network-pack/v1`. It contains two chronological periods, three
resource zones, one constrained ETYS-style cut set, an unconstrained England
fallback connection and one signed interconnector landing.

It is a contract and teaching fixture, not a representation of the GB network.
The corridors are computational routing edges. They are not physical lines and
must not be given voltage or impedance fields. Replace every synthetic value and
record its source before using a derived pack for research.

Run the contract checks from the repository root:

```powershell
py -3.10 -m unittest discover -s tests -p "test_prompt96_zonal_contracts.py" -v
```

The file checksums bind each role to `manifest.json`. The additional
`scientific_sha256` binds the assembled, typed contract so changing a member and
rewriting only its file checksum still fails validation.
