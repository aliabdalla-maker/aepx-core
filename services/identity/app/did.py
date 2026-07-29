"""did:key support — RFC-0006, hardening Law 1 (Identity Before Interaction).

did:key is self-certifying: the DID itself encodes the public key, so
resolving one never needs a registry, a running chain, or any external
lookup — unlike did:ethr/did:sol, which is exactly why it's the method
used here rather than a heavier chain-anchored alternative.

Encoding: an Ed25519 public key, multicodec-prefixed (0xed 0x01 —
ed25519-pub, per https://github.com/multiformats/multicodec), then
multibase base58btc-encoded (leading 'z') — e.g. did:key:z6Mk...
"""
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, PublicFormat, NoEncryption
import base58

_ED25519_MULTICODEC_PREFIX = bytes([0xed, 0x01])


def _build_document(did: str, multibase: str) -> dict:
    vm_id = f"{did}#{multibase}"
    return {
        "@context": [
            "https://www.w3.org/ns/did/v1",
            "https://w3id.org/security/suites/ed25519-2020/v1",
        ],
        "id": did,
        "verificationMethod": [{
            "id": vm_id,
            "type": "Ed25519VerificationKey2020",
            "controller": did,
            "publicKeyMultibase": multibase,
        }],
        "authentication": [vm_id],
        "assertionMethod": [vm_id],
    }


def create_did() -> dict:
    """Generates a fresh Ed25519 keypair and returns its did:key DID, DID
    Document, and private key (hex). The private key is returned once and
    never persisted server-side — same dev-only-secret posture as
    IDENTITY_JWT_SECRET in app/main.py; callers own safekeeping it.
    """
    private_key = ed25519.Ed25519PrivateKey.generate()
    pub_bytes = private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    multibase = "z" + base58.b58encode(_ED25519_MULTICODEC_PREFIX + pub_bytes).decode()
    did = f"did:key:{multibase}"
    priv_bytes = private_key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    return {
        "did": did,
        "did_document": _build_document(did, multibase),
        "private_key_hex": priv_bytes.hex(),
    }


def resolve_did(did: str) -> dict:
    """Decodes a did:key string back into its DID Document. Raises
    ValueError on anything malformed or on an unsupported DID method —
    callers should turn that into a 400, not a 500.
    """
    parts = did.split(":")
    if len(parts) != 3 or parts[0] != "did" or parts[1] != "key":
        raise ValueError(f"unsupported DID method — expected 'did:key:...', got '{did}'")
    multibase = parts[2]
    if not multibase.startswith("z"):
        raise ValueError("unsupported multibase encoding — expected base58btc ('z' prefix)")
    try:
        raw = base58.b58decode(multibase[1:])
    except Exception as e:
        raise ValueError(f"invalid base58btc encoding: {e}")
    if len(raw) != 34 or raw[:2] != _ED25519_MULTICODEC_PREFIX:
        raise ValueError("not a recognised Ed25519 did:key (unexpected multicodec prefix or key length)")
    return _build_document(did, multibase)
