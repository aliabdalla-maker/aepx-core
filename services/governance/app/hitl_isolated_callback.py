"""Opt-in local process-isolated callback runner; NOT wired to live dispatch.

Only importable, explicitly allowlisted adapter entrypoints are accepted.
This is a prototype for offline testing; provider idempotency and network
isolation remain separate mandatory deployment controls.
"""
import importlib
import multiprocessing as mp
import queue

class CallbackIsolationError(RuntimeError):
    pass

def _child(entrypoint, arguments, output):
    try:
        module_name, function_name = entrypoint.rsplit(":", 1)
        fn = getattr(importlib.import_module(module_name), function_name)
        result = fn(**arguments)
        if result is not None and not isinstance(result, bool):
            output.put(("error", None))
        else:
            output.put(("ok", result))
    except BaseException:
        output.put(("error", None))

def run_isolated_callback(*, entrypoint, arguments, allowed_entrypoints,
                          timeout_seconds=5):
    """Run a bounded importable adapter in a fresh spawned process.

    Timeout/termination means UNKNOWN remote outcome, never safe retry.
    Caller must reconcile a precommitted uncertain receipt independently.
    """
    if (not isinstance(entrypoint, str) or
        not isinstance(allowed_entrypoints, (set, frozenset)) or
        entrypoint not in allowed_entrypoints or
        entrypoint.count(":") != 1):
        raise CallbackIsolationError("callback not allowlisted")
    if (not isinstance(arguments, dict) or
        not all(isinstance(k, str) for k in arguments)):
        raise ValueError("keyword argument mapping required")
    if (isinstance(timeout_seconds, bool) or
        not isinstance(timeout_seconds, (int, float)) or
        not 0 < timeout_seconds <= 60):
        raise ValueError("bounded timeout required")
    ctx = mp.get_context("spawn")
    output = ctx.Queue(maxsize=1)
    process = ctx.Process(target=_child, args=(entrypoint, arguments, output))
    process.daemon = True
    try:
        process.start()
        process.join(timeout_seconds)
        if process.is_alive():
            process.terminate()
            process.join(1)
            if process.is_alive():
                process.kill()
                process.join(1)
            raise CallbackIsolationError("callback timed out: outcome uncertain")
        if process.exitcode != 0:
            raise CallbackIsolationError("callback process exited abnormally")
        try:
            status, result = output.get(timeout=0.5)
        except queue.Empty as exc:
            raise CallbackIsolationError("callback returned no verified outcome") from exc
        if status != "ok":
            raise CallbackIsolationError("callback failed: outcome uncertain")
        return result
    finally:
        if process.pid is not None and process.is_alive():
            process.kill()
            process.join(1)
        output.close()
        output.join_thread()
