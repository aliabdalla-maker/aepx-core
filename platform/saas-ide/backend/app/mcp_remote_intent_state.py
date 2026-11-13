"""Pure remote-intent transition policy. Does not persist or execute requests."""
from enum import Enum

class IntentTransitionDenied(ValueError):
    pass

class IntentState(str, Enum):
    RESERVED = "reserved"
    DISPATCHED = "dispatched"
    UNCERTAIN = "uncertain"
    SUCCEEDED = "succeeded"
    FAILED = "failed"

_ALLOWED = {
    IntentState.RESERVED: frozenset({IntentState.DISPATCHED, IntentState.FAILED}),
    IntentState.DISPATCHED: frozenset({IntentState.UNCERTAIN, IntentState.SUCCEEDED, IntentState.FAILED}),
    IntentState.UNCERTAIN: frozenset({IntentState.SUCCEEDED, IntentState.FAILED}),
    IntentState.SUCCEEDED: frozenset(),
    IntentState.FAILED: frozenset(),
}

def validate_transition(current, target, *, provider_evidence=False):
    if type(current) is not IntentState or type(target) is not IntentState:
        raise IntentTransitionDenied("typed state required")
    if target not in _ALLOWED[current]:
        raise IntentTransitionDenied("illegal remote execution state transition")
    if target in (IntentState.SUCCEEDED, IntentState.FAILED) and current != IntentState.RESERVED:
        if provider_evidence is not True:
            raise IntentTransitionDenied("provider evidence required for terminal outcome")
    return target
