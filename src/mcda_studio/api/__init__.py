"""HTTP API over the Stage 1 domain, services and storage (FastAPI).

The API contains no mathematics and no editing rules: every endpoint delegates to
``mcda_studio.services`` / ``mcda_studio.storage``, and every request and response body is a
domain model (``Project``, ``MavtResult``, ...), so the saved-file schema stays the single source
of truth. See ``docs/api/contract.md``.
"""

from mcda_studio.api.app import create_app

__all__ = ["create_app"]
