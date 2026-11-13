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
