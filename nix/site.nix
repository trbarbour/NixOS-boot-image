# Site settings for the boot images: the root SSH public key and auto-install
# (design: plans/2026-10-21T135252Z-site-settings-pure-images-design.md).
#
# A *site* is a directory holding `pre-nixos-site.nix`, a plain attribute set
# (paths resolve relative to the site directory, e.g. `rootKey = ./root_key.pub`).
# It lives outside git (any directory, or the gitignored ./site/), and reaches a
# pure build as the flake input `site` (`--override-input site path:<dir>`) or
# as the `site` argument of `lib.mkBootImage`.  All functions here are pure.
{ lib }:

let
  settingNames = [ "rootKey" "autoInstall" "primaryConsole" ];
  consoles = [ "serial" "display" ];

  # PRE_NIXOS_AUTO_INSTALL as pre_nixos.py reads it; anything else is an error
  # rather than a silent "off".
  parseEnvBool = name: value:
    let v = lib.toLower value; in
    if lib.elem v [ "1" "true" "yes" "on" ] then true
    else if lib.elem v [ "" "0" "false" "no" "off" ] then false
    else throw "pre-nixos: ${name}=${builtins.toJSON value} is not a boolean (use 1/0, true/false, yes/no, on/off).";
in
rec {
  siteFileName = "pre-nixos-site.nix";

  # Typed settings of one site: `null` means "not set by this site".
  validateSite = where: raw:
    let
      unknown = lib.filter (name: !(lib.elem name settingNames)) (builtins.attrNames raw);
      rootKey = raw.rootKey or null;
      autoInstall = raw.autoInstall or null;
      primaryConsole = raw.primaryConsole or null;
    in
    if !builtins.isAttrs raw then
      throw "pre-nixos site ${where}: expected an attribute set"
    else if unknown != [ ] then
      throw "pre-nixos site ${where}: unknown setting(s) ${lib.concatStringsSep ", " unknown}; known: ${lib.concatStringsSep ", " settingNames}"
    else if !(rootKey == null || builtins.isPath rootKey) then
      throw "pre-nixos site ${where}: rootKey must be a path (e.g. ./root_key.pub), not ${builtins.typeOf rootKey}"
    else if rootKey != null && !builtins.pathExists rootKey then
      throw "pre-nixos site ${where}: rootKey ${toString rootKey} does not exist"
    else if !(autoInstall == null || builtins.isBool autoInstall) then
      throw "pre-nixos site ${where}: autoInstall must be true or false, not ${builtins.typeOf autoInstall}"
    else if !(primaryConsole == null || lib.elem primaryConsole consoles) then
      throw "pre-nixos site ${where}: primaryConsole must be one of ${lib.concatStringsSep ", " (map builtins.toJSON consoles)}, not ${builtins.toJSON primaryConsole}"
    else
      { inherit rootKey autoInstall primaryConsole; };

  # A site directory.  Its settings file is required, so a mistyped override
  # or an incomplete site fails instead of silently building an image with no
  # key (PR #319 review); the repo's default site has an explicit `{ }`.
  readSite = dir:
    let file = dir + "/${siteFileName}"; in
    if builtins.pathExists file then validateSite (toString file) (import file)
    else throw "pre-nixos site ${toString dir}: no ${siteFileName} (a site directory must contain it; see README \"Site settings\")";

  # Combine a site with the legacy environment variables (design D2c): the
  # environment only fills settings the site leaves unset, and a disagreement
  # is an error.  `env` is { rootKey = string; autoInstall = string; }, the raw
  # PRE_NIXOS_ROOT_KEY / PRE_NIXOS_AUTO_INSTALL values ("" when unset or when
  # evaluating purely).  Result: { rootKey = path | null; autoInstall = bool;
  # primaryConsole = "serial" | "display" | null }, null meaning the format's
  # default (design plans/2026-10-23T022949Z-primary-console-design.md).
  resolveSettings = { site, env }:
    let
      envKey =
        if env.rootKey == "" then null
        else if builtins.pathExists env.rootKey then
          builtins.path { path = env.rootKey; name = "pre-nixos-root-key.pub"; }
        else throw "pre-nixos: PRE_NIXOS_ROOT_KEY=${env.rootKey} does not exist";
      envAuto = if env.autoInstall == "" then null else parseEnvBool "PRE_NIXOS_AUTO_INSTALL" env.autoInstall;
      rootKey =
        if site.rootKey == null then envKey
        else if envKey != null && builtins.readFile envKey != builtins.readFile site.rootKey then
          throw "pre-nixos: the site's rootKey and PRE_NIXOS_ROOT_KEY differ; set only one"
        else site.rootKey;
      autoInstall =
        if site.autoInstall == null then envAuto == true
        else if envAuto != null && envAuto != site.autoInstall then
          throw "pre-nixos: the site's autoInstall and PRE_NIXOS_AUTO_INSTALL differ; set only one"
        else site.autoInstall;
    in
    { inherit rootKey autoInstall; inherit (site) primaryConsole; };
}
