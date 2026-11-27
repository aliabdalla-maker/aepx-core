#!/usr/bin/env bash
# Builds the Endpoint Security client (universal arm64 + x86_64). Signing:
#  development (SIP disabled test Mac): codesign -s - --entitlements AavEndpointSecurity.entitlements -f out/AavEndpointSecurity
#  production: Developer ID + the Apple-granted endpoint-security entitlement in a provisioning profile, then
#  notarise; grant Full Disk Access via MDM (register B-04).
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p out
for arch in arm64 x86_64; do
  swiftc -O -target "$arch-apple-macos12.0" -framework EndpointSecurity -framework Foundation main.swift \
    -o "out/AavEndpointSecurity-$arch"
done
lipo -create out/AavEndpointSecurity-arm64 out/AavEndpointSecurity-x86_64 -output out/AavEndpointSecurity
codesign -s - --entitlements AavEndpointSecurity.entitlements -f out/AavEndpointSecurity
echo "built out/AavEndpointSecurity (ad-hoc signed; needs the Apple ES entitlement to run)"
