
## Dependabot Alert #1: ecdsa Minerva timing attack (dismissed 2 Jul 2026)
GHSA scope: python-ecdsa SigningKey.sign_digest(), P-256 curve.
Verified via grep: btc_verify.py and app.py contain zero calls to
SigningKey, sign_digest, or .sign(). Verification-only usage confirmed
by design (Sprint 3 spec). Advisory states signature verification is
explicitly unaffected. No patched version exists; risk accepted as
not applicable rather than mitigated.
