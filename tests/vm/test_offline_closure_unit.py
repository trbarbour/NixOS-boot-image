"""Unit tests for tests/vm/offline_closure.py (no Nix needed)."""

from __future__ import annotations

from tests.vm.offline_closure import missing_from_closure, required_input_outputs

# Shape of ``nix derivation show --recursive`` in Nix 2.34 (observed 2026-10-18).
SHOW = {
    "version": 4,
    "derivations": {
        "aaa-script.drv": {
            "inputs": {
                "drvs": {
                    "bbb-stdenv-linux.drv": {"dynamicOutputs": {}, "outputs": ["out"]},
                    "ccc-e2fsprogs.drv": {"dynamicOutputs": {}, "outputs": ["bin"]},
                },
                "srcs": ["ddd-default-builder.sh"],
            },
            "outputs": {"out": {"path": "eee-script"}},
        },
        "bbb-stdenv-linux.drv": {"outputs": {"out": {"path": "fff-stdenv-linux"}}},
        "ccc-e2fsprogs.drv": {
            "outputs": {"bin": {"path": "ggg-e2fsprogs-bin"}, "dev": {"path": "hhh-e2fsprogs-dev"}}
        },
    },
}


def test_only_the_used_outputs_of_direct_inputs_are_required() -> None:
    assert required_input_outputs(SHOW, "/nix/store/aaa-script.drv") == {
        "/nix/store/fff-stdenv-linux",
        "/nix/store/ggg-e2fsprogs-bin",
    }


def test_missing_from_closure_reports_absent_paths_sorted() -> None:
    required = {"/nix/store/fff-stdenv-linux", "/nix/store/ggg-e2fsprogs-bin"}
    assert missing_from_closure(required, ["/nix/store/ggg-e2fsprogs-bin"]) == [
        "/nix/store/fff-stdenv-linux"
    ]
    assert missing_from_closure(required, required) == []


def test_dry_run_list_from_a_serial_transcript() -> None:
    """The VM's transcript as read on 2026-11-09: terminal escapes and
    "\\r\\r\\n" endings (#340; the first parser found nothing and passed)."""

    from tests.vm.test_offline_install_closure_vm import _to_build

    transcript = (
        "cat /tmp/offline-dry-run.txt\r\r\n"
        "\x1b[?2004l\rthese 2 derivations will be built:\r\r\n"
        "  /nix/store/2kbbzfsz1hzd21yj0h989s3z40cgrp58-stage0-posix-1.9.1-source.drv\r\r\n"
        "  /nix/store/ah9bgvfcw4px7wzj3x3ijf88w04fx6l3-nixos-system-nixos-26.05pre-git.drv\r\r\n"
        "dry-run-exit=0\r\r\n"
    )
    expected = [
        "/nix/store/2kbbzfsz1hzd21yj0h989s3z40cgrp58-stage0-posix-1.9.1-source.drv",
        "/nix/store/ah9bgvfcw4px7wzj3x3ijf88w04fx6l3-nixos-system-nixos-26.05pre-git.drv",
    ]
    assert _to_build(transcript) == expected
    # The same text after a text-mode read (each "\r" becomes a newline).
    assert _to_build(transcript.replace("\r\n", "\n").replace("\r", "\n")) == expected
    # As BootImageVM.run returns it: escapes removed and every line stripped.
    from tests.vm.controller import clean_command_output

    assert _to_build(clean_command_output(transcript, "cat /tmp/offline-dry-run.txt")) == expected
