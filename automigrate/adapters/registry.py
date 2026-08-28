"""
Adapter Registry.

Central registry of all known framework adapters.
Provides framework auto-detection and lookup by name.

Adding a new framework:
    1. Create your adapter in automigrate/adapters/<framework>/adapter.py
    2. Import it here and add it to _ADAPTERS.
"""

from __future__ import annotations

from pathlib import Path

from automigrate.adapters.base import FrameworkAdapter


# ---------------------------------------------------------------------------
# Lazy imports to avoid circular deps at module load time
# ---------------------------------------------------------------------------

def _load_adapters() -> list[type[FrameworkAdapter]]:
    """Lazily import and return all known adapter classes."""
    from automigrate.adapters.angular.adapter import AngularAdapter
    from automigrate.adapters.react.adapter import ReactAdapter
    return [AngularAdapter, ReactAdapter]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def list_adapters() -> list[type[FrameworkAdapter]]:
    """Return all registered adapter classes."""
    return _load_adapters()


def detect_framework(project_path: str) -> FrameworkAdapter | None:
    """Auto-detect the framework used in a project.

    Iterates adapters in registration order and returns the first
    adapter whose .detect() method returns True.

    Args:
        project_path: Absolute path to the project root directory.

    Returns:
        An instantiated FrameworkAdapter, or None if no adapter matched.
    """
    path = Path(project_path).resolve()
    for adapter_cls in _load_adapters():
        if adapter_cls.detect(str(path)):
            return adapter_cls()
    return None


def get_adapter(framework_name: str) -> FrameworkAdapter:
    """Return an adapter instance by its name slug.

    Args:
        framework_name: e.g. "angular", "react", "vue".

    Raises:
        ValueError: if no adapter is registered with that name.
    """
    for adapter_cls in _load_adapters():
        if adapter_cls.name == framework_name.lower():
            return adapter_cls()
    registered = [cls.name for cls in _load_adapters()]
    raise ValueError(
        f"No adapter found for framework {framework_name!r}. "
        f"Registered: {registered}"
    )


def get_adapter_for_migration(framework_name: str, migration_type: str) -> FrameworkAdapter:
    """Return an adapter instance, validating that it supports the migration type.

    Args:
        framework_name: e.g. "angular".
        migration_type: e.g. "control_flow".

    Raises:
        ValueError: if adapter not found or migration type not supported.
    """
    adapter = get_adapter(framework_name)
    if not adapter.get_migration(migration_type):
        supported = [m.id for m in adapter.get_migrations()]
        raise ValueError(
            f"Framework {framework_name!r} does not support migration type "
            f"{migration_type!r}. Supported: {supported}"
        )
    return adapter
