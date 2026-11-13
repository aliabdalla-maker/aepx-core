"""Offline fixtures for spawned callback process tests."""
import time

def succeeds():
    return True

def rejects():
    return False

def hangs():
    time.sleep(10)
    return True

def fails():
    raise RuntimeError("test-only failure")

def crashes():
    import os
    os._exit(17)  # disposable offline child only; simulate abrupt process death
