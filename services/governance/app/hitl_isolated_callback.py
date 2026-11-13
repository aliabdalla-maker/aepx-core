"""Opt-in local process-isolated callback runner; NOT wired to live dispatch.

Only importable, explicitly allowlisted adapter entrypoints are accepted.
This is a prototype for offline testing; provider idempotency and network
isolation remain separate mandatory deployment controls.
"""
import importlib
import multiprocessing as mp
import time

class CallbackIsolationError(RuntimeError):
    pass

def _child(entrypoint, arguments, output):
    try:
        module_name, function_name = entrypoint.rsplit(":", 1)
        fn = getattr(importlib.import_module(module_name), function_name)
        result = fn(**arguments)
        if result is not None and not isinstance(result, bool):
            output.send(("error", None))
        else:
            output.send(("ok", result))
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
    receiver, sender = ctx.Pipe(duplex=False)
    process = ctx.Process(target=_child, args=(entrypoint, arguments, sender))
    process.daemon = True
    try:
        process.start()
        sender.close()
        deadline = time.monotonic() + timeout_seconds
        # Read before join: a Queue feeder may deadlock if joined before drain.
        # A single bounded Pipe message avoids that feeder thread.
        if not receiver.poll(max(0, deadline - time.monotonic())):
            raise CallbackIsolationError("callback timed out or exited: outcome uncertain")
        try:
            status, result = receiver.recv()
        except (EOFError, OSError) as exc:
            raise CallbackIsolationError("callback IPC failed: outcome uncertain") from exc
        process.join(max(0, deadline - time.monotonic()))
        if process.is_alive():
            raise CallbackIsolationError("callback failed to exit: outcome uncertain")
        if process.exitcode != 0 or status != "ok":
            raise CallbackIsolationError("callback failed: outcome uncertain")
        return result
    finally:
        receiver.close()
        sender.close()
        if process.pid is not None and process.is_alive():
            process.terminate()
            process.join(1)
            if process.is_alive():
                process.kill()
                process.join(1)
