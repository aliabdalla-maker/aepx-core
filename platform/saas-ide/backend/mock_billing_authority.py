"""Offline mock billing authority CLI, run in a separate isolated process.

Receives receipt JSON on stdin and signs using a separately provisioned private
Ed25519 key file. No network, no app database access, no production credentials.
Do not deploy this test authority as a production billing provider.
"""
import base64
import json
import os
import sys
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from app.billing29 import canonical_receipt

def main():
    keyfile=os.environ.get("IDE_MOCK_BILLING_PRIVATE_KEY_FILE")
    if not keyfile:
        raise RuntimeError("Independent mock authority key file required")
    raw=Path(keyfile).read_bytes()
    if len(raw)!=32:
        raise ValueError("Expected raw 32-byte Ed25519 private key")
    receipt=json.loads(sys.stdin.read(8192))
    signature=Ed25519PrivateKey.from_private_bytes(raw).sign(canonical_receipt(receipt))
    print(json.dumps({"receipt":receipt,"signature":base64.b64encode(signature).decode()},
                     separators=(",",":")))
if __name__=="__main__":
    main()
