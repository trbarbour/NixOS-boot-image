{
  description = "Pre-NixOS setup tool";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";
    flake-utils.url = "github:numtide/flake-utils";
    disko.url = "github:nix-community/disko";
    disko.inputs.nixpkgs.follows = "nixpkgs";
    # Site settings (root SSH public key, auto-install), kept outside git and
    # supplied purely: `--override-input site path:<dir>`.  The default is the
    # repo's empty site (nix/site.nix; design
    # plans/2026-10-21T135252Z-site-settings-pure-images-design.md).
    site = { url = "path:./nix/site-default"; flake = false; };
  };

  outputs = { self, nixpkgs, flake-utils, disko, site, ... }:
    let
      inherit (flake-utils.lib) eachDefaultSystem;
      lib = nixpkgs.lib;
      preNixosVersion = lib.strings.removeSuffix "\n" (builtins.readFile ./pre_nixos/VERSION);

      siteLib = import ./nix/site.nix { inherit lib; };
      # Legacy, impure fallback (design D2c): only read under --impure, and only
      # fills settings the site leaves unset.
      envSettings = {
        rootKey = builtins.getEnv "PRE_NIXOS_ROOT_KEY";
        autoInstall = builtins.getEnv "PRE_NIXOS_AUTO_INSTALL";
      };
      settingsFor = siteDir: siteLib.resolveSettings { site = siteLib.readSite siteDir; env = envSettings; };
      flakeSettings = settingsFor site.outPath;

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

      makePreNixosPackage = { system, rootKey ? null }:
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
          postPatch = pkgs.lib.optionalString (rootKey != null) ''
            cp ${rootKey} pre_nixos/root_key.pub
          '';
          postInstall = pkgs.lib.optionalString (rootKey != null) ''
            install -Dm0644 ${rootKey} "$out/${pkgs.python3.sitePackages}/pre_nixos/root_key.pub"
          '';
          # The embedded key, for the site-* flake checks.
          passthru.rootKey = rootKey;
          postFixup = ''
            for prog in pre-nixos pre-nixos-detect-storage pre-nixos-tui; do
              wrapProgram "$out/bin/$prog" --prefix PATH : ${requiredToolBinPath}
            done
          '';
        };

      # One definition for every platform's boot image (reqs §2.9 R-P1;
      # AArch64 plan §3.2): the platform's stock NixOS image plus pre-nixos.
      # `settings` (nix/site.nix resolveSettings) is the one source of both the
      # key embedded in the package and the module's options, so the image's
      # login notice and its behaviour cannot disagree (design D4).
      mkPreInstaller = { system, imageModules, settings }:
        let
          package = makePreNixosPackage { inherit system; inherit (settings) rootKey; };
        in
        nixpkgs.lib.nixosSystem {
          inherit system;
          modules = [
            ({ ... }: { nixpkgs.overlays = [ diskoOverlay (_: _: { pre-nixos = package; }) ]; })
            preNixosModule
          ] ++ imageModules ++ [
            ({ ... }: {
              services.pre-nixos.enable = true;
              services.pre-nixos.rootKey = settings.rootKey;
              services.pre-nixos.autoInstall = settings.autoInstall;
            })
          ];
        };

      preInstallerSystem = "x86_64-linux";

      # The stock AArch64 SD image (Raspberry Pi 4 family, e.g. CM4), unchanged
      # apart from pre-nixos (R-P2): Hydra's sd_image job, i.e. the *installer*
      # variant (installation-device profile: root/nixos console logins without
      # a password, as on the x86 ISO).  The bare sd-image-aarch64.nix leaves
      # root locked (E5 run4, 2026-10-19).  Built on x86_64 under binfmt
      # emulation (R-T1; scripts/lib/aarch64_emulation.sh).
      aarch64System = "aarch64-linux";
      stockSdImageModules = [ "${nixpkgs}/nixos/modules/installer/sd-card/sd-image-aarch64-installer.nix" ];

      # Boot-image formats (design D5): the system each runs on, the stock
      # image modules, and the image attribute.
      formats = {
        iso = {
          system = preInstallerSystem;
          imageModules = [
            "${nixpkgs}/nixos/modules/installer/cd-dvd/iso-image.nix"
            "${nixpkgs}/nixos/modules/installer/cd-dvd/installation-cd-minimal.nix"
          ];
          image = config: config.system.build.isoImage;
        };
        sd = {
          system = aarch64System;
          imageModules = stockSdImageModules ++ [
            # The x86 ISO gets this from its CD modules; the SD modules set none.
            ({ lib, ... }: { system.stateVersion = lib.mkDefault lib.trivial.release; })
            # The installed system boots from NVMe via the Pi firmware and an
            # NVMe-capable U-Boot (AArch64 plan item 8; R-B1).
            ({ config, pkgs, ... }: {
              services.pre-nixos.installedBoot = "rpi4-uboot-extlinux";
              services.pre-nixos.rpiFirmware = pkgs.callPackage ./nix/rpi4-nvme-firmware.nix {
                inherit (config.sdImage) populateFirmwareCommands;
                ubootRpi4Nvme = pkgs.callPackage ./nix/uboot-rpi4-nvme.nix { };
              };
            })
          ];
          image = config: config.system.build.sdImage;
        };
      };

      formatOf = format:
        formats.${format} or (throw "pre-nixos: unknown boot-image format ${builtins.toJSON format}; supported: ${lib.concatStringsSep ", " (builtins.attrNames formats)}");

      # A boot image's NixOS configuration from a format and a site directory
      # (default: the flake input `site`).  Exported as lib.mkBootConfiguration.
      mkBootConfigurationWith = { format, settings }:
        let f = formatOf format; in
        mkPreInstaller { inherit (f) system imageModules; inherit settings; };
      mkBootConfiguration = { format, site ? null }:
        mkBootConfigurationWith {
          inherit format;
          settings = if site == null then flakeSettings else settingsFor site;
        };

      # Flake checks for the site settings (design §2).  They pass an empty
      # environment explicitly, so they are deterministic even under --impure.
      noEnv = { rootKey = ""; autoInstall = ""; };
      fixtureSite = ./tests/fixtures/site-example;
      otherKey = ./tests/fixtures/other_root_key.pub;
      fails = value: !(builtins.tryEval (builtins.deepSeq value value)).success;
      siteChecks = {
        # A site's key and auto-install reach both images, package and module alike.
        site-settings =
          let
            want = builtins.readFile (fixtureSite + "/root_key.pub");
            settings = siteLib.resolveSettings { site = siteLib.readSite fixtureSite; env = noEnv; };
            ok = format:
              let c = mkBootConfigurationWith { inherit format settings; }; in
              c.pkgs.pre-nixos.rootKey != null
              && builtins.readFile c.pkgs.pre-nixos.rootKey == want
              && builtins.readFile c.config.services.pre-nixos.rootKey == want
              && c.config.systemd.services.pre-nixos.environment.PRE_NIXOS_AUTO_INSTALL == "1";
          in
          assert lib.assertMsg (ok "iso" && ok "sd") "a site's rootKey/autoInstall did not reach both images";
          true;
        # The repo's own default site embeds nothing and does not auto-install.
        site-default =
          let
            settings = siteLib.resolveSettings { site = siteLib.readSite ./nix/site-default; env = noEnv; };
            c = mkBootConfigurationWith { format = "iso"; inherit settings; };
          in
          assert lib.assertMsg
            (settings == { rootKey = null; autoInstall = false; }
              && c.pkgs.pre-nixos.rootKey == null
              && !(c.config.systemd.services.pre-nixos.environment ? PRE_NIXOS_AUTO_INSTALL))
            "the default site must embed no key and leave auto-install off";
          true;
        # Typos and wrong types are evaluation errors, not ignored.
        site-validation =
          assert lib.assertMsg
            (fails (siteLib.validateSite "t" { rootkey = otherKey; })
              && fails (siteLib.validateSite "t" { rootKey = "/etc/ssh/key.pub"; })
              && fails (siteLib.validateSite "t" { rootKey = ./tests/fixtures/no-such.pub; })
              && fails (siteLib.validateSite "t" { autoInstall = "yes"; })
              && fails (formatOf "dvd")
              && fails (siteLib.resolveSettings { site = siteLib.validateSite "t" { }; env = noEnv // { autoInstall = "maybe"; }; })
              && !(fails (siteLib.validateSite "t" { })))
            "site validation accepted an invalid setting or rejected an empty site";
          true;
        # The legacy environment only fills unset settings; disagreement is an error.
        site-env-conflict =
          let
            fixture = siteLib.readSite fixtureSite;
            empty = siteLib.validateSite "t" { };
            fixtureKey = toString (fixtureSite + "/root_key.pub");
            filled = siteLib.resolveSettings { site = empty; env = { rootKey = toString otherKey; autoInstall = "1"; }; };
          in
          assert lib.assertMsg
            (fails (siteLib.resolveSettings { site = fixture; env = noEnv // { rootKey = toString otherKey; }; })
              && fails (siteLib.resolveSettings { site = fixture; env = noEnv // { autoInstall = "0"; }; })
              && !(fails (siteLib.resolveSettings { site = fixture; env = { rootKey = fixtureKey; autoInstall = "1"; }; }))
              && builtins.readFile filled.rootKey == builtins.readFile otherKey
              && filled.autoInstall)
            "the site/environment precedence or conflict detection is wrong";
          true;
      };

      preInstallerConfig = mkBootConfiguration { format = "iso"; };
      preInstallerPackage = preInstallerConfig.pkgs.pre-nixos;
      aarch64Config = mkBootConfiguration { format = "sd"; };
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
          else makePreNixosPackage { inherit system; };
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
            ubootRpi4Nvme = aarch64Config.pkgs.callPackage ./nix/uboot-rpi4-nvme.nix { };
            rpi4NvmeFirmware = aarch64Config.config.services.pre-nixos.rpiFirmware;
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
        } // pkgs.lib.optionalAttrs (system == preInstallerSystem) (
          builtins.mapAttrs (name: passed: assert passed; pkgs.runCommand name { } "touch $out") siteChecks
        ) // pkgs.lib.optionalAttrs (system == preInstallerSystem) {
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
      # Build a boot image for your own site from a flake of your own:
      #   outputs = { pre-nixos, ... }: {
      #     packages.aarch64-linux.default =
      #       pre-nixos.lib.mkBootImage { format = "sd"; site = ./.; };
      #   };
      # `format`: "iso" (x86_64-linux) or "sd" (aarch64-linux); `site`: a
      # directory with pre-nixos-site.nix (nix/site.nix).
      lib = {
        inherit mkBootConfiguration;
        mkBootImage = { format, site ? null }@args:
          (formatOf format).image (mkBootConfiguration args).config;
      };
      nixosModules.pre-nixos = preNixosModule;
      nixosConfigurations.pre-installer = preInstallerConfig;
      nixosConfigurations.pre-installer-aarch64 = aarch64Config;
    };
}
