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
