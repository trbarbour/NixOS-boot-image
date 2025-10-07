# Serial console parameter verification

## Context
- Date: 2025-10-07T04:01:53Z (UTC)
- Observer: Automation agent
- Task: Ensure the boot image retains serial console output after init by verifying kernel parameters.

## Verification steps
1. Evaluated the `boot.kernelParams` attribute of the `pre-installer` configuration: `nix eval --json .#nixosConfigurations.pre-installer.config.boot.kernelParams`.
2. Confirmed the resulting list includes both `"console=ttyS0,115200n8"` and `"console=tty0"`, along with the expected `loglevel=4` value.

## Outcome
- No configuration changes required; the pre-installer build already propagates the required serial console parameters.
- The existing GRUB extra configuration (serial input/output) remains valid, so serial logs persist across boot.

## Next actions
- Proceed with follow-up performance measurements once provisioning/network fixes land (see queue).
