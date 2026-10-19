{
  description = "Pre-NixOS setup tool";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";
    flake-utils.url = "github:numtide/flake-utils";
    disko.url = "github:nix-community/disko";
    disko.inputs.nixpkgs.follows = "nixpkgs";
  };

  outputs = { self, nixpkgs, flake-utils, disko, ... }:
    let
      inherit (flake-utils.lib) eachDefaultSystem;
      lib = nixpkgs.lib;
      preNixosVersion = lib.strings.removeSuffix "\n" (builtins.readFile ./pre_nixos/VERSION);

      rootPubEnv = builtins.getEnv "PRE_NIXOS_ROOT_KEY";
      rootPubPath = "${builtins.toString ./.}/pre_nixos/root_key.pub";
      warnNoKey = message: builtins.trace message null;
      missingKeyWarning =
        "PRE_NIXOS_ROOT_KEY was not provided or visible during evaluation; continuing without embedding a root SSH key. Pass --impure to `nix build` if you expect environment variables to be available.";
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
                  "PRE_NIXOS_ROOT_KEY did not resolve to a readable file; continuing without embedding a root SSH key"
                  null
            else if builtins.pathExists rootPubPath then
              builtins.toPath rootPubPath
            else
              warnNoKey missingKeyWarning;
        in
        if resolvedPath != null then
          builtins.path { path = resolvedPath; }
        else
          null;

      # RAID arrays get no write-intent bitmap (reqs §2.2).  disko has no option
      # for it, and since mdadm 4.4 omitting --bitmap makes mdadm ask, so the
      # `echo 'y'` disko pipes in would answer that question instead of
      # "Continue creating array?".  --replace-fail turns an upstream change of
      # this line into a build failure.
      diskoOverlay = final: _: {
        disko = disko.packages.${final.stdenv.hostPlatform.system}.disko.overrideAttrs (old: {
          postPatch = (old.postPatch or "") + ''
            substituteInPlace lib/types/mdadm.nix \
              --replace-fail "mdadm --create " "mdadm --create --bitmap=none "
          '';
        });
      };

      pkgsFor = system:
        import nixpkgs {
          inherit system;
          overlays = [ diskoOverlay ];
        };

      preNixosModule = import ./modules/pre-nixos.nix;
      requiredToolNames = [ "disko" "gptfdisk" "mdadm" "lvm2" "ethtool" "util-linux" "kmod" ];

      makePreNixosPackage = system:
        let
          pkgs = pkgsFor system;
          requiredToolPackages = pkgs.lib.attrVals requiredToolNames pkgs;
          requiredToolBinPath = pkgs.lib.makeBinPath requiredToolPackages;
        in
        pkgs.python3Packages.buildPythonApplication {
          pname = "pre-nixos";
          version = preNixosVersion;
          src = ./.;
          pyproject = true;
          nativeBuildInputs = with pkgs; [ makeWrapper python3Packages.setuptools python3Packages.wheel ];
          propagatedBuildInputs = requiredToolPackages;
          postPatch = pkgs.lib.optionalString (rootPub != null) ''
            cp ${rootPub} pre_nixos/root_key.pub
          '';
          postInstall = pkgs.lib.optionalString (rootPub != null) ''
            install -Dm0644 ${rootPub} "$out/${pkgs.python3.sitePackages}/pre_nixos/root_key.pub"
          '';
          postFixup = ''
            for prog in pre-nixos pre-nixos-detect-storage pre-nixos-tui; do
              wrapProgram "$out/bin/$prog" --prefix PATH : ${requiredToolBinPath}
            done
          '';
        };

      # One definition for every platform's boot image (reqs §2.9 R-P1;
      # AArch64 plan §3.2): the platform's stock NixOS image plus pre-nixos.
      mkPreInstaller = { system, imageModules }:
        let
          package = makePreNixosPackage system;
        in
        nixpkgs.lib.nixosSystem {
          inherit system;
          modules = [
            ({ ... }: { nixpkgs.overlays = [ diskoOverlay (_: _: { pre-nixos = package; }) ]; })
            preNixosModule
          ] ++ imageModules ++ [
            ({ ... }: { services.pre-nixos.enable = true; })
          ];
        };

      preInstallerSystem = "x86_64-linux";
      preInstallerConfig = mkPreInstaller {
        system = preInstallerSystem;
        imageModules = [
          "${nixpkgs}/nixos/modules/installer/cd-dvd/iso-image.nix"
          "${nixpkgs}/nixos/modules/installer/cd-dvd/installation-cd-minimal.nix"
        ];
      };
      preInstallerPackage = preInstallerConfig.pkgs.pre-nixos;

      # The stock AArch64 SD image (Raspberry Pi 4 family, e.g. CM4), unchanged
      # apart from pre-nixos (R-P2).  Built on x86_64 under binfmt emulation
      # (R-T1; scripts/lib/aarch64_emulation.sh).
      aarch64System = "aarch64-linux";
      stockSdImageModules = [ "${nixpkgs}/nixos/modules/installer/sd-card/sd-image-aarch64.nix" ];
      aarch64Config = mkPreInstaller {
        system = aarch64System;
        imageModules = stockSdImageModules ++ [
          # As the x86 installer modules do; the SD image module sets none.
          ({ lib, ... }: { system.stateVersion = lib.mkDefault lib.trivial.release; })
        ];
      };
      stockAarch64Config = nixpkgs.lib.nixosSystem {
        system = aarch64System;
        modules = stockSdImageModules;
      };

      # R-P2: pre-nixos must not change the stock image's boot chain or kernel
      # console parameters.  Evaluation only (no aarch64 build needed).
      bootSettings = config: {
        kernelParams = config.boot.kernelParams;
        grub = config.boot.loader.grub.enable;
        extlinux = config.boot.loader.generic-extlinux-compatible.enable;
        firmware = config.sdImage.populateFirmwareCommands;
        kernel = config.boot.kernelPackages.kernel.version;
      };
    in
    eachDefaultSystem (system:
      let
        pkgs = pkgsFor system;
        preNixosPackage =
          if system == preInstallerSystem then preInstallerPackage
          else if system == aarch64System then aarch64Config.pkgs.pre-nixos
          else makePreNixosPackage system;
      in {
        packages =
          if system == preInstallerSystem then {
            default = preInstallerConfig.config.system.build.isoImage;
            bootImage = preInstallerConfig.config.system.build.isoImage;
            pre-nixos = preNixosPackage;
          } else if system == aarch64System then {
            default = preNixosPackage;
            pre-nixos = preNixosPackage;
            bootImageSd = aarch64Config.config.system.build.sdImage;
          } else {
            default = preNixosPackage;
            pre-nixos = preNixosPackage;
          };
        checks = {
          pre-nixos-propagates-required-tools =
            let
              propagatedNames =
                builtins.map
                  (drv:
                    if drv ? pname then drv.pname else (builtins.parseDrvName drv.name).name)
                  preNixosPackage.propagatedBuildInputs;
              missingTools =
                pkgs.lib.filter (tool: !(pkgs.lib.elem tool propagatedNames)) requiredToolNames;
            in
            # `assert` forces the check; a let-bound assertMsg was never
            # evaluated (verified 2026-10-19: a literal `false` still passed).
            assert pkgs.lib.assertMsg
              (missingTools == [])
              "pre-nixos must propagate required tools: ${builtins.toString missingTools}";
            pkgs.runCommand "pre-nixos-propagates-required-tools" {} ''
              touch $out
            '';
        } // pkgs.lib.optionalAttrs (system == preInstallerSystem) {
          stock-aarch64-boot-settings =
            let
              ours = bootSettings aarch64Config.config;
              stock = bootSettings stockAarch64Config.config;
            in
            assert pkgs.lib.assertMsg (ours == stock)
              "pre-nixos changes the stock AArch64 boot settings (R-P2): ours=${builtins.toJSON ours} stock=${builtins.toJSON stock}";
            pkgs.runCommand "stock-aarch64-boot-settings" {} ''
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
            shellHook = ''
              shared_tmp=''${PRE_NIXOS_BOOT_IMAGE_TMPDIR:-/tmp/boot-image-shared-tmp}
              if [ ! -d "$shared_tmp" ]; then
                install -d -m 1777 "$shared_tmp"
              else
                chmod 1777 "$shared_tmp"
              fi
              export PRE_NIXOS_BOOT_IMAGE_TMPDIR="$shared_tmp"
              export TMPDIR="$shared_tmp"
            '';
          };
        };
      }) // {
      nixosModules.pre-nixos = preNixosModule;
      nixosConfigurations.pre-installer = preInstallerConfig;
      nixosConfigurations.pre-installer-aarch64 = aarch64Config;
    };
}
