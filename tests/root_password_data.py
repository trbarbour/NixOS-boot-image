"""The test root password (reqs R-A1; task queue item 45).

The VM images and tests/fixtures/site-example use this hash; the plain
password is test-only and protects nothing.
"""

TEST_ROOT_PASSWORD = "pre-nixos-vm-test"
# mkpasswd -m yescrypt, from nixpkgs' mkpasswd 5.6.6 (2026-11-10).
TEST_ROOT_PASSWORD_HASH = "$y$j9T$Y5LoFQB1W5dkf/fSia4AG0$RT34fdiAmo.qsfnbxOlakOqbBf5uAPh6JCLP2JLgC.."
