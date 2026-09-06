"""Shared pytest fixtures for the ClaimFlow backend test suite.

Currently empty: Group A (Types layer) tests exercise plain dataclasses, enums, and
pure functions with no fixtures required. Later groups (config, db, repositories,
services, api) will add fixtures here -- e.g. a temp sqlite database, seeded
policies/claims, and a FastAPI TestClient.
"""
