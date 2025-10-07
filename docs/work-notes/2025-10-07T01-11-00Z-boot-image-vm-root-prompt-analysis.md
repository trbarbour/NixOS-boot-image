# Boot Image VM Root Prompt Investigation Log (2025-10-07T01:11:00Z)

## Objective
Determine the definitive cause of the boot-image VM test's login failure, where the automation never observes a root prompt after the automatic `nixos` login.

## Background
- Prior runs of `tests/test_boot_image_vm.py` stall after the `nixos` auto-login banner prints. The `_login` helper emits the `__USER__` marker, proving `id -u` returned `1000`, but the fixture never progresses to the `sudo -i` step before timing out.
- Hypothesis from earlier notes: either `sudo` was missing or `pexpect` failed to match the colourised prompt. Need to validate which scenario is occurring.

## Experiments

### 1. Inspect saved serial console log for escape sequences
- Loaded the archived serial transcript `docs/boot-logs/2025-10-06T15-54-30Z-serial.log` as raw bytes.
- Observed that immediately after the `__USER__` marker the prompt bytes are `\x1b[1;32m[\x1b]0;nixos@nixos: ~\x07nixos@nixos:~]\$\x1b[0m` followed by a trailing space.
- This confirms the console prints ANSI colour codes and bracketed-paste toggles around the visible `nixos@nixos:~]$` prompt.

### 2. Reproduce the prompt-match failure with the existing regex
- Took the captured byte sequence and evaluated `re.search(r"nixos@.*\\$ ", prompt)`. The result is `False`, meaning our current expectation does **not** match the coloured prompt.
- Because `_login` calls `expect([r"root@.*# ", r"# ", r"nixos@.*\\$ "])` immediately after reading the `__USER__` marker, the unmatched ANSI wrapper prevents `pexpect` from recognising that the shell is ready. `_login` therefore never executes `sudo -i` and eventually times out.

### 3. Cross-check pytest failure buffer
- Reviewed `docs/test-reports/2025-10-06T15-54-30Z-boot-image-vm-test.log`; the captured `pexpect` buffer at timeout shows the same escape-laden prompt string, corroborating the byte-level inspection.

## Results
- All gathered evidence points to prompt detection failing because of ANSI control sequences emitted by the default Bash prompt.
- There is no indication that `sudo` is missing; the automation never reaches the point where it would attempt `sudo -i` because the prompt regex blocks progress earlier.

## Conclusion
The boot-image VM login fails because `_login` expects an uncoloured `nixos@...$` prompt. The real prompt wraps the username and host inside colour and bracketed-paste escape sequences, so the regex never matches and the handshake stops before privilege escalation. This explains the currently observed stall, but the investigation does **not** prove it is the only contributing factor; we must verify the hypothesis by implementing the matcher fix and rerunning the test.

## Open Questions and Remaining Hypotheses
- Serial logging still appears to cease once systemd takes over (see Session 6 notes). If console output remains incomplete after the prompt fix, revisit kernel boot parameters.
- The pre-nixos provisioning warning (`Storage detection encountered an error`) may indicate a separate fault that could surface again once login proceeds.
- We have not yet confirmed whether `sudo` behaves correctly under the VM environment because `_login` never executed it. After broadening the prompt matcher we should explicitly verify `sudo -i` completes.

## Next Actions
1. Update the task queue to record the identified root cause and add a follow-up implementation task to harden prompt matching.
2. Prototype a prompt-normalisation helper or extend the regex to accept escape sequences before re-running the VM test.
3. After rerunning the test, assess whether the serial console and pre-nixos provisioning hypotheses still require targeted investigations.
