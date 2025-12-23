# VM harness hardening — 2025-12-23T01:59:37Z (UTC)

## Context
- Previous VM runs failed to retain root privileges after `sudo -i` / `su -` because background serial noise matched prompt patterns and corrupted `id -u` parsing.
- Continuing the modular VM plan to stabilize the login/escalation flow before rerunning the full suite.

## Actions
- Added prompt configuration with a unique sentinel to absorb late boot messages before capturing the shell prompt.
- Switched UID detection to unique markers parsed via regex so stray serial output cannot be mistaken for the `id -u` result.
- Threaded the new prompt configuration through initial login plus `sudo -i` / `su -` escalation paths.

## Next steps
- Re-run the VM integration suite once container time allows and record timings/artifacts in `notes/` and the ledger.
- If root escalation still fails, inspect the new login transcript markers to see whether sudo/su actually succeeded.
