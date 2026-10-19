"""Optional Langfuse tracing for ModelClient calls (langfuse Python SDK v5, explicit generations).

On only when LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are set. Without them `langfuse` is
never imported and generation() yields None, so callers behave exactly as before.

Each call is one generation named after the target (teacher/base/tuned). Its input is the
messages list and its output the assistant content, which is the shape
scripts/langfuse_export.py turns back into Distil traces.
"""

from __future__ import annotations

import atexit
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from slmkit.settings import env

_lock = threading.Lock()
_client: Any = None
_initialised = False


def enabled() -> bool:
    return bool(env("LANGFUSE_PUBLIC_KEY") and env("LANGFUSE_SECRET_KEY"))


def get_client():
    """The shared Langfuse client, or None when tracing is off. Created once, thread-safe."""
    global _client, _initialised
    if _initialised:
        return _client
    with _lock:
        if not _initialised:
            if enabled():
                from langfuse import Langfuse

                _client = Langfuse(
                    public_key=env("LANGFUSE_PUBLIC_KEY"),
                    secret_key=env("LANGFUSE_SECRET_KEY"),
                    base_url=env("LANGFUSE_HOST", "https://cloud.langfuse.com"),
                )
                # The SDK also shuts down at exit; flushing here first makes sure short CLI
                # runs (one `make invoke`) send their spans before the process is gone.
                atexit.register(flush)
            _initialised = True
    return _client


def flush() -> None:
    if _client is not None:
        _client.flush()


@contextmanager
def generation(
    *,
    name: str,
    model: str,
    messages: list[dict],
    model_parameters: dict | None = None,
    tags: list[str] | None = None,
    metadata: dict[str, str] | None = None,
    session_id: str | None = None,
) -> Iterator[Any]:
    """Wrap one model call. Yields the Langfuse generation (call .update(output=...)), or None.

    `tags` and `metadata` are propagated to the trace so dashboards can filter on them;
    Langfuse caps each propagated metadata value at 200 characters, so keep them short.
    """
    lf = get_client()
    if lf is None:
        yield None
        return
    from langfuse import propagate_attributes

    with (
        propagate_attributes(
            trace_name=name, tags=tags, metadata=metadata, session_id=session_id
        ),
        lf.start_as_current_observation(
            as_type="generation",
            name=name,
            model=model,
            input=messages,
            model_parameters=model_parameters,
        ) as gen,
    ):
        try:
            yield gen
        except Exception as exc:
            # level=ERROR also keeps failed calls out of `make traces` (the export skips them)
            gen.update(level="ERROR", status_message=str(exc) or type(exc).__name__)
            raise
