# Security policy

## Reporting

Report a security issue through GitHub Issues on this repository. Do not
include live secrets, keys, or real credentials in a report; describe the
issue and how to reproduce it with a throwaway test key.

## Posture

The protocol is fail-closed: it refuses to start without a key, and there is
no fallback secret. Keys are environment-only and must be at least 32 bytes.
