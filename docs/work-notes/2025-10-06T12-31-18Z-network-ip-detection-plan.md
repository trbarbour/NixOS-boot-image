# Network IP Detection Improvement Plan

## Context
The `pre_nixos.network.get_ip_address` helper currently parses the output of
`ip -o -4 addr show`. This string parsing is brittle because the output format
can vary with iproute2 releases, locales, or when multiple addresses are present
on the interface. A more reliable approach is to consume the JSON output exposed
by `ip -j`, which allows structured extraction of IPv4 addresses and clearer
error handling.

## Goals
* Make IP detection resilient to formatting differences and multiple address
  entries.
* Preserve existing behaviour for callers that expect `None` when no IPv4
  address is available or when the command fails.
* Extend unit tests to cover the JSON-parsing path and error handling cases.

## Tasks
1. Refactor `pre_nixos.network.get_ip_address` to invoke `ip -j -4 addr show`
   and parse the JSON response. The helper should gracefully handle
   `subprocess.CalledProcessError` and `json.JSONDecodeError`, returning `None`
   when parsing fails.
2. Update `get_lan_status` to rely on the refactored helper (no behaviour
   change expected, but confirm compatibility).
3. Adjust unit tests in `tests/test_network.py` to supply JSON fixtures instead
   of whitespace-delimited output. Add a regression test that exercises the
   resilience to malformed JSON by returning `None`.
4. Run the full pytest suite to ensure no regressions and capture the results
   in the work log.

## Execution Notes
* Refactored `pre_nixos.network.get_ip_address` to consume the JSON output from
  `ip -j -4 addr show`, including defensive checks for unexpected payloads.
* Extended `tests/test_network.py` with JSON-based fixtures and a regression
  test covering malformed command output.
* Test run: `pytest` → 71 passed, 2 skipped (`tests/test_boot_image_vm.py`).
