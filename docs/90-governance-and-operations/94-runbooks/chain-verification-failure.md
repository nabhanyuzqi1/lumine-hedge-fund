# Runbook — Audit Hash-Chain Verification Failure (P0)

- **Status:** active · **Drilled:** no
- **Owner:** architects / cio
- **Last-reviewed:** 2026-08-02
- **Review-cadence:** 90

## Trigger
The daily chain-verification job reports a broken `prev_hash` / `self_hash`
link in the journal or `lineage_records` (ADR-0017).

## Why this is P0
A broken chain means the audit trail may have been tampered with. Until the
cause is known and the integrity boundary is re-established, no decision on
the system can be trusted as auditable. Halt trading.

## Steps
1. **Halt trading.** Engage the kill switch (CIO authority). No autonomous
   restart (ADR-0010).
2. **Freeze writes.** Stop the app role's INSERT on the affected table.
3. **Identify the break row.** The verification job reports the first row
   whose hash doesn't match. Inspect that row and its predecessor.
4. **Compare against WORM anchor.** Pull the most recent anchored chain head
   from S3 Object Lock. Compare to the live chain. The WORM copy is the
   tamper-evident reference.
   - If WORM matches the live chain up to row N and diverges after →
     tampering or bug after the last anchor.
   - If WORM itself diverges → the anchor was compromised (escalate to
     security incident, `SECURITY.md`).
5. **Determine cause.** Likely classes: (a) a code bug in canonicalization,
   (b) an out-of-band SQL write (DBA, migration), (c) tampering.
6. **Restore integrity.** If a code bug: fix, recompute hashes forward from
   the last good anchor, re-anchor. If tampering: treat as security incident;
   do not overwrite — preserve evidence.
7. **Resume.** CIO clears the kill switch only after chain verification
   passes end-to-end and the cause is documented in an ADR.

## Detection vs prevention
- Hash chain **detects** tampering.
- WORM anchor **prevents** tampering of anchored history.
- Both must be healthy to resume.
