"""Hard wall-clock subprocess deadline for isolated, tool-free provider invocations."""
import multiprocessing as mp
import os
import queue

def _child(q, fn, args, kwargs):
    try:
        q.put(("ok",fn(*args,**kwargs)))
    except BaseException:
        q.put(("error","Execution failed"))

def hard_deadline(fn, *args, seconds: int = 30, **kwargs):
    if os.getenv("IDE_EXTERNAL_EXECUTION_ENABLED")!="true":
        raise PermissionError("External execution disabled")
    if not 1<=seconds<=60:
        raise ValueError("Invalid deadline")
    # spawn prevents inheriting DB sockets/connection pools from parent.
    ctx=mp.get_context("spawn")
    q=ctx.Queue(maxsize=1)
    process=ctx.Process(target=_child,args=(q,fn,args,kwargs),daemon=True)
    process.start()
    process.join(seconds)
    if process.is_alive():
        process.terminate()
        process.join(2)
        if process.is_alive():
            process.kill()
            process.join()
        raise TimeoutError("Worker deadline exceeded")
    try:
        state,value=q.get(timeout=1)
    except queue.Empty:
        raise RuntimeError("Worker exited without result")
    if state!="ok":
        raise RuntimeError(value)
    return value
