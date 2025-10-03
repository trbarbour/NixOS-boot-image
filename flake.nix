{
  description = "Pre-NixOS setup tool";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-24.05";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils, ... }:
    let
      inherit (flake-utils.lib) eachDefaultSystem;

      rootPubEnv = builtins.getEnv "PRE_NIXOS_ROOT_KEY";
      rootPubPath = "${builtins.toString ./.}/pre_nixos/root_key.pub";
      rootPub =
        let
          resolvedPath =
            if rootPubEnv != "" then
              let
                candidate = builtins.toString rootPubEnv;
              in
              if builtins.pathExists candidate then
                builtins.toPath candidate
              else
                builtins.trace
                  "PRE_NIXOS_ROOT_KEY did not resolve to a readable file; continuing without embedding a root key"
                  null
            else if builtins.pathExists rootPubPath then
              builtins.toPath rootPubPath
            else
              null;
        in
        if resolvedPath != null then
          builtins.path { path = resolvedPath; }
        else
          null;

      pkgsFor = system: nixpkgs.legacyPackages.${system};

      preNixosModule = import ./modules/pre-nixos.nix;

      makePreNixosPackage = system:
        let
          pkgs = pkgsFor system;
        in
        pkgs.python3Packages.buildPythonApplication {
          pname = "pre-nixos";
          version = "0.1.0";
          src = ./.;
          pyproject = true;
          nativeBuildInputs = with pkgs.python3Packages; [ setuptools wheel ];
          propagatedBuildInputs =
            pkgs.lib.attrVals
              [ "disko" "gptfdisk" "mdadm" "lvm2" "ethtool" "util-linux" ]
              pkgs;
          postPatch = pkgs.lib.optionalString (rootPub != null) ''
            cp ${rootPub} pre_nixos/root_key.pub
          '';
        };

      preInstallerSystem = "x86_64-linux";
      preInstallerPackage = makePreNixosPackage preInstallerSystem;
      preInstallerOverlay = _: _: { pre-nixos = preInstallerPackage; };

      preInstallerConfig = nixpkgs.lib.nixosSystem {
        system = preInstallerSystem;
        modules = [
          ({ ... }: { nixpkgs.overlays = [ preInstallerOverlay ]; })
          preNixosModule
          "${nixpkgs}/nixos/modules/installer/cd-dvd/iso-image.nix"
          "${nixpkgs}/nixos/modules/installer/cd-dvd/installation-cd-minimal.nix"
          ({ config, ... }: { services.pre-nixos.enable = true; })
        ];
      };
    in
    eachDefaultSystem (system:
      let
        pkgs = pkgsFor system;
        preNixosPackage =
          if system == preInstallerSystem
          then preInstallerPackage
          else makePreNixosPackage system;
      in {
        packages =
          if system == preInstallerSystem then {
            default = preInstallerConfig.config.system.build.isoImage;
            bootImage = preInstallerConfig.config.system.build.isoImage;
            pre-nixos = preNixosPackage;
          } else {
            default = preNixosPackage;
            pre-nixos = preNixosPackage;
          };
        checks = {
          pre-nixos-propagates-required-tools =
            let
              requiredTools = [ "disko" "gptfdisk" "mdadm" "lvm2" "ethtool" "util-linux" ];
              propagatedNames =
                builtins.map
                  (drv:
                    if drv ? pname then drv.pname else (builtins.parseDrvName drv.name).name)
                  preNixosPackage.propagatedBuildInputs;
              missingTools =
                pkgs.lib.filter (tool: !(pkgs.lib.elem tool propagatedNames)) requiredTools;
              _ =
                pkgs.lib.assertMsg
                  (missingTools == [])
                  "pre-nixos must propagate required tools: ${builtins.toString missingTools}";
            in
            pkgs.runCommand "pre-nixos-propagates-required-tools" {} ''
              touch $out
            '';
        };
        devShells = {
          default = pkgs.mkShell {
            buildInputs = [ pkgs.python3 pkgs.python3Packages.pytest ];
          };
          bootImageTest = pkgs.mkShell {
            buildInputs = [
              pkgs.python3
              pkgs.python3Packages.pytest
              pkgs.python3Packages.pexpect
              pkgs.qemu
              pkgs.nix
            ];
          };
        };
      }) // {
      nixosModules.pre-nixos = preNixosModule;
      nixosConfigurations.pre-installer = preInstallerConfig;
    };
}
