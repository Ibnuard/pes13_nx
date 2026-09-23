# Wine-NX 32-bit guest exception backport

Copyright 2026 Wine-NX contributors. LGPL-2.1-or-later, as the source files.

Adapted from danfromtico/autorun commits e04029a51e91ed965242b20741e2730b7c9a33d5
(guest exception dispatch) and 8f3e5f78f5 (callback EAX result).

The local Box64 0.4.4 compiler recovery uses cancelFillBlock only when the
translator lock, current_helper and fillblock_active indicate an active
recovery target. Unlike the older upstream code, it does not call
CancelBlock64 before that jump: the 0.4.4 state machine owns cleanup.

Patches have exact, unambiguous context checks and apply to the isolated
PERF11 runtime baseline. tools/build-perf15.py composes them with PERF14's
mapping guards and builds the matching native PE winebox64 module. No
broader AMD64 or newer memory subsystem changes are imported.

The native ABI fixture includes a host TEB stub for its already-present
context-reset callback and checks the fault metadata/diagnostic cap. The
separate project fixture tests recovery helpers; these host tests do not
replace Switch execution testing.
