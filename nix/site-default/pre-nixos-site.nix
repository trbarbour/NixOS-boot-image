# The repository's default site: no root key, no auto-install.  Replace it at
# build time with your own site directory, kept outside git:
#   nix build .#bootImage --override-input site path:/path/to/site
# (see nix/site.nix and README "Site settings").
{ }
