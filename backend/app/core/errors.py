class RunNotFound(LookupError):
    pass


class RunBusy(RuntimeError):
    pass


class DemoDisabled(PermissionError):
    pass
