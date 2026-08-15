# Post-mortem 0002: iLanguage verifyToken silently failed all tokens

Status: resolved (in iLanguage commit `0210f3a`)

## Executive summary

iLanguage's backend `auth.ts` had zero automated tests. The first test
suite added (vitest, 22 tests, covering the exported crypto helpers)
immediately caught a live bug: `verifyToken` round-tripped the HMAC
signature through a UTF-8 string decode, silently mangling any signature
containing bytes ≥ 0x80 that are not valid UTF-8 — which HMAC signatures
routinely contain. Result: `verifyToken` returned null for essentially
every token, and nothing had ever noticed.

## Impact

Every access-token verification in the backend's auth flow was failing at
the verify step in the environment where this path ran. Because the
failure mode was "return null" (designed to mean invalid token) rather
than a crash, it presented as auth-not-working, not as an exception with
a stack trace. Discovery required the first-ever unit test on the
function.

## Timeline

1. Backend migrated from Cloudflare Workers to Node.js + MySQL + Redis;
   auth logic ported with token helpers left module-private.
2. Harness integration audit listed "backend has no automated tests" as a
   known gap.
3. Vitest scaffolding added; `sha256`, `b64encode`, `b64decode`,
   `signToken`, `verifyToken`, `maskPhone`, `maskEmail` exported for
   testability (no behavior change).
4. The `signToken → verifyToken` roundtrip test failed:
   `verifyToken` returned `null` for a token `signToken` had just
   produced.
5. Root cause found in the old line:
   `Uint8Array.from(b64decode(sigB64), c => c.charCodeAt(0))` where
   `b64decode = Buffer.from(str,'base64').toString('utf-8')`.

## Root cause

Two decodings conflated: base64→bytes (what was needed) and
bytes→UTF-8-string→charCodes (what was written). `Buffer.from(x,
'base64').toString('utf-8')` is lossy for arbitrary byte sequences; UTF-8
replacement characters make the round-trip unequal, so the HMAC verify
compares against corrupted bytes and fails. The bug is invisible to any
signature whose bytes happen to be valid UTF-8 — a coin-flip per token,
so occasional manual "it worked" checks during development could pass.

## What the gates missed

There were no gates: no tests on the backend, and the function was
module-private so even ad-hoc testing required an export. TypeScript
type-checking passes because every step is well-typed — the bug is
semantic, not type-level.

## Fix and the rule it produced

Fix: `const sigBytes = Buffer.from(sigB64, 'base64')` — base64 straight
to bytes, no UTF-8 detour.

Rules:

1. **Decode base64 directly to bytes when bytes are what you need.**
   Never route arbitrary binary through a UTF-8 string.
2. **The first test on untested code is a bug hunt, not a formality** —
   write the roundtrip property (sign→verify, encode→decode) first; that
   class of test found this bug in one assertion.
3. Exporting pure helpers for testability is a legitimate refactor; "it
   was private" is not a reason a function stays untested.
