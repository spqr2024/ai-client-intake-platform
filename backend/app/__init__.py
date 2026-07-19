"""AI Client Intake Platform — backend package.

`__version__` is the single source of truth for the application version. It is
surfaced by the OpenAPI schema, `/health/live` and `/health/ready`, and must
match the newest entry in CHANGELOG.md (CI asserts this).
"""

__version__ = "2.3.0"
