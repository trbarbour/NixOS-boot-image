"""Fixture shim for the VM test split.

This file will import and re-export fixtures as they migrate out of
``tests/test_boot_image_vm.py`` so that the test names remain stable. Keeping the
shim in place avoids churn in call sites while helpers are relocated into
modules under ``tests/vm``.
"""
