# Test fixture for the flake checks site-* (nix/site.nix).  The key is a
# throwaway generated for this fixture; its private half was not kept.  The
# hash is of the test password "pre-nixos-vm-test" (mkpasswd -m yescrypt).
{
  rootKey = ./root_key.pub;
  autoInstall = true;
  rootHashedPassword = "$y$j9T$Y5LoFQB1W5dkf/fSia4AG0$RT34fdiAmo.qsfnbxOlakOqbBf5uAPh6JCLP2JLgC..";
}
