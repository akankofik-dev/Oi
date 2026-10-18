import inspect


def filter_init_kwargs(cls, kwargs):
    try:
        sig = inspect.signature(cls.__init__)
    except (TypeError, ValueError):
        return dict(kwargs)
    params = list(sig.parameters.values())
    for p in params:
        if p.kind == inspect.Parameter.VAR_KEYWORD:
            return dict(kwargs)
    accepted = set()
    for p in params:
        accepted.add(p.name)
    out = {}
    for k, v in kwargs.items():
        if k in accepted:
            out[k] = v
    return out
