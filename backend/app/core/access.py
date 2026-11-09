from dataclasses import dataclass


@dataclass(frozen=True)
class WorkspaceAccess:
    workspace_id: str


def get_workspace_access() -> WorkspaceAccess:
    """Local single-workspace scope; replace with authenticated membership later.

    Never infer this scope from a client-supplied workspace header or body field.
    Registering a project does not grant permission to run tests against it.
    """
    return WorkspaceAccess(workspace_id="local")
