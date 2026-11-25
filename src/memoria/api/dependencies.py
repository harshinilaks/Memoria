from memoria.core.config import settings


def get_namespace() -> str:
    """Resolve the namespace for the current caller.

    Phase 1 has no authentication: every request acts as the configured development
    identity. This is the single place to replace with real auth later; clients cannot
    choose their namespace.
    """
    return settings.dev_namespace
