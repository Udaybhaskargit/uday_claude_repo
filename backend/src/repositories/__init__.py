"""Repository layer (Group D): SQLite data-access for domain entities.

Repositories depend only on Types (`src.types`) and the connection factory
(`src.db`) -- never on Service or API layers, per `.claude/architecture.md`.
"""
