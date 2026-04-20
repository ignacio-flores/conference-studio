from __future__ import annotations

import hashlib
from functools import wraps
from typing import Callable


_PATCHED = False


def _accepts_usedforsecurity(func: Callable) -> bool:
    try:
        func(usedforsecurity=False)
    except TypeError as exc:
        return "usedforsecurity" not in str(exc)
    return True


def _wrap_constructor(func: Callable) -> Callable:
    @wraps(func)
    def wrapped(*args, **kwargs):
        kwargs.pop("usedforsecurity", None)
        return func(*args, **kwargs)

    return wrapped


def install_hashlib_usedforsecurity_compat() -> None:
    """Allow newer libraries to pass usedforsecurity on older Python builds."""
    global _PATCHED
    if _PATCHED:
        return

    names = ("md5", "sha1", "sha224", "sha256", "sha384", "sha512")
    for name in names:
        func = getattr(hashlib, name, None)
        if func is not None and not _accepts_usedforsecurity(func):
            setattr(hashlib, name, _wrap_constructor(func))

    original_new = hashlib.new

    try:
        original_new("md5", usedforsecurity=False)
    except TypeError as exc:
        if "usedforsecurity" in str(exc):

            @wraps(original_new)
            def wrapped_new(name, data=b"", **kwargs):
                kwargs.pop("usedforsecurity", None)
                return original_new(name, data, **kwargs)

            hashlib.new = wrapped_new

    _PATCHED = True
