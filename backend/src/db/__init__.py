"""Repository layer -- infra half (E3-S1).

`src.db` holds the raw SQLite plumbing (connection factory, migration
runner) that every `src.repositories.*` module builds on. Per
`folder-structure.md`, this package imports only `src.types` and
`src.config` -- never `src.services`, `src.api`, or `src.repositories`
itself.
"""
