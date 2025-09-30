# Storage Planning and Provisioning Design

## Background

The boot image builder needs to take a high-level description of how the
installation media should partition, format, and mount the target disks. The
previous implementation translated the plan directly into imperative shell
commands (`sgdisk`, `mkfs`, `mount`, etc.). That direct approach made it hard to
support complex layouts, reason about idempotence, or share logic with other
NixOS installers.

Disko already provides a declarative DSL for describing storage topologies and a
robust implementation for applying them. By generating a Disko configuration and
invoking Disko itself, we can reuse that logic instead of reimplementing it.

## Goals

* Accept the existing high-level plan schema without change.
* Translate the plan into a Disko configuration that mirrors the desired disk
  topology.
* Invoke Disko to materialise the partition tables, format filesystems, and
  mount everything.
* Keep the Disko invocation isolated so it can be unit tested by swapping out
  the command runner.

## Architecture

```
┌────────────┐      ┌─────────────────────┐      ┌────────────┐
│  Planner   │ ---> │ Disko configuration │ ---> │ Disko CLI │
└────────────┘      └─────────────────────┘      └────────────┘
```

1. **Planner** – converts the domain plan into a normalised representation of
   the disk topology. The core responsibility is to expand convenient shortcut
   fields (for example, `filesystem.format`) into the structure that Disko
   expects under `disko.devices`.
2. **Disko configuration** – serialised from the normalised representation into
   a standalone `.nix` file containing the `disko.devices` attribute set. The
   serialisation is deterministic so unit tests can assert on the generated
   output.
3. **Disko CLI** – we run Disko via
   `nix run github:nix-community/disko/latest -- …`, passing the generated file
   and mode flags (e.g. `destroy,format,mount`). The executor coordinates the
   temporary file lifecycle and command invocation.

## Planner Output

The planner returns a `DiskoPlan` object that contains:

* `config`: Ordered mapping that becomes the `disko.devices` attribute set.
* `mode`: Comma-separated Disko modes (defaults to `destroy,format,mount`).
* `flags`: Additional CLI flags to append after `--mode` (defaults to empty).

Every disk entry is normalised to the following shape:

```nix
{
  disko.devices = {
    disk = {
      <disk-name> = {
        device = "/dev/<device>";
        type = "disk";
        content = {
          type = "gpt"; # overridable via plan["scheme"]
          partitions = {
            <partition-name> = {
              size = "<size>";
              # optional: type, start, end, etc.
              content = {
                type = "filesystem";
                format = "ext4"; # or the requested format
                mountpoint = "/";
                mountOptions = [ "subvol=@" ];
              };
            };
          };
        };
      };
    };
  };
}
```

If the plan provides an explicit `content` attribute for a partition (for
example, for LUKS or LVM), it is passed through verbatim. Otherwise the planner
builds a `filesystem` entry from the shortcut fields.

## Disko Execution Flow

1. The executor calls `generate_disko_plan(plan)` to obtain a `DiskoPlan`.
2. The plan is rendered to a temporary `.nix` file through `DiskoPlan.render()`.
3. We assemble the Disko command:
   ```
   nix --experimental-features "nix-command flakes" \
     run github:nix-community/disko/latest -- \
     --mode destroy,format,mount <optional flags…> /tmp/disko-plan-XXXX.nix
   ```
4. The executor runs the command using a pluggable runner (defaulting to
   `subprocess.run(cmd, check=True)`).
5. The temporary file is deleted after Disko exits (successfully or otherwise).

## Error Handling

* The planner raises `ValueError` when required fields (e.g. `device` or
  `partitions`) are missing.
* The executor lets `subprocess.CalledProcessError` propagate so callers can
  surface Disko failures to the user.
* Temporary files are removed in a `finally` block to avoid leaking secrets or
  stale configurations on disk.

## Testing Strategy

* Unit tests cover the planner transformation so complex storage layouts can be
  validated without touching real disks.
* Executor tests inject a fake runner to capture the generated Disko command and
  inspect the temporary file contents.

This design keeps the planner focused on pure data transformation, while Disko
handles the imperative disk operations.
