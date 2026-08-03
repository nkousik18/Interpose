"""Python implementations of packs' custom policy hooks (docs/INTERPOSE_SCOPING.md
Section 9.8). Parallel to `policies/packs/` (the declarative YAML) -- that directory
holds the data, this package holds the small amount of code a pack's `custom`
effects reference by name. Each submodule registers its functions against
`interpose.policies.custom`'s decorators at import time; `interpose.gateway.app`
imports every pack module here at startup.
"""
