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

      # Image file names say which pre-nixos built them: the version and the
      # git commit ("-dirty" for uncommitted changes), then nixpkgs' label and
      # the system, e.g. pre-nixos-0.21.0-g4852185-26.05.20261015.26f4107-aarch64-linux.img.zst.
      # nixpkgs' default names only carry its own version, so two pre-nixos
      # images were indistinguishable once copied out of the store.
      sourceRev = "g" + (self.shortRev or self.dirtyShortRev or "unknown");
      imageBaseName = { label, system }: "pre-nixos-${preNixosVersion}-${sourceRev}-${label}-${system}";
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
      mkPreInstaller = { system, imageModules, settings, console }:
        let
          package = makePreNixosPackage { inherit system; inherit (settings) rootKey; };
        in
        nixpkgs.lib.nixosSystem {
          inherit system;
          modules = [
            ({ ... }: { nixpkgs.overlays = [ diskoOverlay (_: _: { pre-nixos = package; }) ]; })
            preNixosModule
          ] ++ imageModules ++ [
            ({ config, ... }: {
              services.pre-nixos.enable = true;
              services.pre-nixos.rootKey = settings.rootKey;
              services.pre-nixos.autoInstall = settings.autoInstall;
              # R-C2, chosen per format by mkBootConfigurationWith.
              services.pre-nixos.primaryConsole = console.primary;
              services.pre-nixos.serialConsole = console.serial;
              # The ISO and SD modules set image.baseName with normal priority.
              image.baseName = lib.mkForce (imageBaseName { inherit system; label = config.system.nixos.label; });
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
          # R-C2.  The ISO lists one serial console, which is the one used.
          primaryConsole = "display";
          serialConsole = null;
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
          # R-C2.  The stock SD image lists two serial consoles, for different
          # boards (nixpkgs: ttyS0 "for Tegra", ttyAMA0 "for QEMU's -machine
          # virt"), and the kernel prefers only one; if it is absent,
          # /dev/console falls back to the display (design F6).  R-P1's Pi 4
          # family uses the mini UART, ttyS0: on the CM4 it carries the console,
          # and there is no ttyAMA0 (design §5).
          primaryConsole = "serial";
          serialConsole = "ttyS0,115200n8";
        };
      };

      # R-C2: the serial console to make primary, taken from the format's own
      # console list (design §5).  A format names one when the list has
      # several; a name outside the list is an error.
      consolesOf = params: map (lib.removePrefix "console=") (builtins.filter (lib.hasPrefix "console=") params);
      isSerialConsole = console: builtins.match "tty[0-9]+(,.*)?" console == null;
      serialConsoleFor = { format, consoles, named }:
        let serials = lib.unique (builtins.filter isSerialConsole consoles); in
        if named != null then
          (if builtins.elem named serials then named
           else throw "pre-nixos: format ${format} names serial console ${builtins.toJSON named}, which is not among its consoles ${builtins.toJSON serials}")
        else if builtins.length serials == 1 then builtins.head serials
        else throw "pre-nixos: format ${format} has serial consoles ${builtins.toJSON serials}; name one in formats.${format}.serialConsole";

      formatOf = format:
        formats.${format} or (throw "pre-nixos: unknown boot-image format ${builtins.toJSON format}; supported: ${lib.concatStringsSep ", " (builtins.attrNames formats)}");

      # A boot image's NixOS configuration from a format and a site directory
      # (default: the flake input `site`).  Exported as lib.mkBootConfiguration.
      mkBootConfigurationWith = { format, settings }:
        let
          f = formatOf format;
          build = console: mkPreInstaller { inherit (f) system imageModules; inherit settings console; };
          # The format's own consoles: the image with nothing appended.
          consoles = consolesOf (build { primary = "display"; serial = null; }).config.boot.kernelParams;
        in
        build {
          primary = if settings.primaryConsole != null then settings.primaryConsole else f.primaryConsole;
          serial = serialConsoleFor { inherit format consoles; named = f.serialConsole; };
        };
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
            (settings == { rootKey = null; autoInstall = false; primaryConsole = null; }
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
              && fails (siteLib.validateSite "t" { primaryConsole = "hdmi"; })
              && fails (formatOf "dvd")
              && fails (siteLib.readSite ./tests/fixtures)
              && fails (siteLib.resolveSettings { site = siteLib.validateSite "t" { }; env = noEnv // { autoInstall = "maybe"; }; })
              && !(fails (siteLib.validateSite "t" { })))
            "site validation accepted an invalid setting or rejected an empty site";
          true;
        # R-C2: the last console= is the primary one (design F1/F2): serial by
        # default on the SD image, display on the ISO, and either on request.
        primary-console =
          let
            lastConsole = format: primaryConsole:
              let
                c = mkBootConfigurationWith {
                  inherit format;
                  settings = { rootKey = null; autoInstall = false; inherit primaryConsole; };
                };
              in
              lib.last (builtins.filter (lib.hasPrefix "console=") c.config.boot.kernelParams);
            serial = "console=ttyS0,115200n8";
            display = "console=tty0";
            got = lib.genAttrs [ "iso" "sd" ] (format: {
              default = lastConsole format null;
              serial = lastConsole format "serial";
              display = lastConsole format "display";
            });
            want = {
              iso = { default = display; inherit serial display; };
              sd = { default = serial; inherit serial display; };
            };
          in
          assert lib.assertMsg (got == want) "primary consoles: ${builtins.toJSON got}";
          true;
        # R-C2 (design §5): the serial console comes from the format's own list:
        # the only one, or the one the format names; never one outside it.
        serial-console-choice =
          let
            chosen = format: (mkBootConfigurationWith {
              inherit format;
              settings = { rootKey = null; autoInstall = false; primaryConsole = null; };
            }).config.services.pre-nixos.serialConsole;
            stockSd = consolesOf stockAarch64Config.config.boot.kernelParams;
          in
          assert lib.assertMsg
            (chosen "iso" == "ttyS0,115200n8"
              && chosen "sd" == "ttyS0,115200n8"
              && builtins.elem (chosen "sd") stockSd
              && serialConsoleFor { format = "t"; consoles = [ "ttyAMA0" "tty0" ]; named = null; } == "ttyAMA0"
              && fails (serialConsoleFor { format = "t"; consoles = stockSd; named = null; })
              && fails (serialConsoleFor { format = "t"; consoles = stockSd; named = "ttyS1,115200n8"; })
              && fails (serialConsoleFor { format = "t"; consoles = [ "tty0" ]; named = null; }))
            "serial console choice: iso=${chosen "iso"} sd=${chosen "sd"} stock=${builtins.toJSON stockSd}";
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
            # The AArch64 image again, so `nix build .#bootImageSd` works on an
            # x86_64 build host (built under emulation); short attribute names
            # resolve within the host's own system (PR #319 review).
            bootImageSd = aarch64Config.config.system.build.sdImage;
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
          # #320: the configuration pre-nixos writes on the target must parse
          # when it starts from nixos-generate-config's real output (fixtures
          # for each loader the generator can pick).
          installed-configuration-parses =
            pkgs.runCommand "installed-configuration-parses" {
              nativeBuildInputs = [ pkgs.python3 pkgs.nix ];
            } ''
              export HOME=$TMPDIR NIX_STATE_DIR=$TMPDIR/nix-state NIX_LOG_DIR=$TMPDIR/nix-log
              export PRE_NIXOS_LOG_FILE=$TMPDIR/pre-nixos.log PYTHONPATH=${./.}
              for variant in extlinux grub efi; do
                for kind in rpi4-uboot-extlinux nixos-default; do
                  root=$TMPDIR/$variant-$kind
                  python3 ${./tests/nix/render_installed_configuration.py} \
                    ${./tests/fixtures/nixos-generate-config}/$variant $root $kind
                  for file in $root/etc/nixos/*.nix; do
                    nix-instantiate --parse "$file" > /dev/null
                  done
                done
              done
              touch $out
            '';
          # #320, design D3: whichever loader nixos-generate-config picked,
          # the installed Pi uses extlinux, and the system evaluates.
          installed-rpi-boot-loader =
            let
              check = variant:
                let
                  config = (nixpkgs.lib.nixosSystem {
                    system = aarch64System;
                    modules = [
                      (./tests/fixtures/nixos-generate-config + "/${variant}/configuration.nix")
                      ./pre_nixos/templates/boot-rpi4-uboot-extlinux.nix
                      { fileSystems."/" = { device = "/dev/main/slash"; fsType = "ext4"; }; }
                    ];
                  }).config;
                  loader = {
                    grub = config.boot.loader.grub.enable;
                    systemdBoot = config.boot.loader.systemd-boot.enable;
                    extlinux = config.boot.loader.generic-extlinux-compatible.enable;
                  };
                in
                assert pkgs.lib.assertMsg
                  (loader == { grub = false; systemdBoot = false; extlinux = true; })
                  "${variant}: installed Pi loader is ${builtins.toJSON loader}";
                builtins.seq config.system.build.toplevel.drvPath true;
            in
            assert builtins.all check [ "extlinux" "grub" "efi" ];
            pkgs.runCommand "installed-rpi-boot-loader" {} ''
              touch $out
            '';
          # Both images are named after this pre-nixos (version and commit).
          image-file-names =
            let
              name = format: (mkBootConfiguration { inherit format; }).config.image.fileName;
              want = format: extension:
                let c = (mkBootConfiguration { inherit format; }).config; in
                "pre-nixos-${preNixosVersion}-${sourceRev}-${c.system.nixos.label}-${formats.${format}.system}.${extension}";
              iso = (mkBootConfiguration { format = "iso"; }).config;
            in
            assert pkgs.lib.assertMsg (name "iso" == want "iso" "iso") "ISO file name is ${name "iso"}";
            assert pkgs.lib.assertMsg (name "sd" == want "sd" "img.zst") "SD file name is ${name "sd"}";
            assert pkgs.lib.assertMsg (pkgs.lib.hasPrefix "pre-nixos-${preNixosVersion}-g" (name "sd"))
              "SD file name ${name "sd"} does not start with the pre-nixos version";
            # The ISO derivation names its file from isoName, not fileName.
            assert pkgs.lib.assertMsg (iso.isoImage.isoName == name "iso")
              "isoName ${iso.isoImage.isoName} differs from image.fileName ${name "iso"}";
            pkgs.runCommand "image-file-names" {} ''
              touch $out
            '';
          # #323: the installed Pi's root is LVM on NVMe behind the BCM2711's
          # PCIe bridge, whose driver is a module that nixos-generate-config
          # cannot detect (it scans PCI devices, not the platform bridge).  The
          # hardware configuration below is what the generator gives the CM4:
          # `nvme` from the PCI scan.
          installed-rpi-initrd-storage =
            let
              config = (nixpkgs.lib.nixosSystem {
                system = aarch64System;
                modules = [
                  ./tests/fixtures/nixos-generate-config/extlinux/configuration.nix
                  ./pre_nixos/templates/boot-rpi4-uboot-extlinux.nix
                  {
                    boot.initrd.availableKernelModules = [ "nvme" ];
                    fileSystems."/" = { device = "/dev/main/slash"; fsType = "ext4"; };
                  }
                ];
              }).config;
              initrd = config.boot.initrd.availableKernelModules ++ config.boot.initrd.kernelModules;
              missing = builtins.filter (m: !(builtins.elem m initrd)) [ "pcie-brcmstb" "nvme" ];
            in
            assert pkgs.lib.assertMsg (missing == [ ])
              "installed Pi initrd lacks ${builtins.toString missing}";
            pkgs.runCommand "installed-rpi-initrd-storage" {} ''
              touch $out
            '';
          # #326: the installed system has one DHCP client on lan, systemd-networkd
          # (which the managed block enables), although nixos-generate-config
          # enables NetworkManager in every configuration.nix it writes.
          installed-network-single-dhcp-client =
            let
              check = variant:
                let
                  config = (nixpkgs.lib.nixosSystem {
                    system = aarch64System;
                    modules = [
                      (./tests/fixtures/nixos-generate-config + "/${variant}/configuration.nix")
                      ./pre_nixos/templates/network-networkd.nix
                      # What the managed block sets (pre_nixos/install.py).
                      {
                        networking.useNetworkd = true;
                        systemd.network.enable = true;
                        fileSystems."/" = { device = "/dev/main/slash"; fsType = "ext4"; };
                      }
                    ];
                  }).config;
                  clients = {
                    networkmanager = config.networking.networkmanager.enable;
                    networkd = config.systemd.network.enable;
                  };
                in
                pkgs.lib.assertMsg (clients == { networkmanager = false; networkd = true; })
                  "${variant}: installed DHCP clients ${builtins.toJSON clients}";
            in
            assert builtins.all check [ "extlinux" "grub" "efi" ];
            pkgs.runCommand "installed-network-single-dhcp-client" {} ''
              touch $out
            '';
          # #324: on the installer, sshd starts once secure_ssh has hardened it,
          # not when pre-nixos.service (which runs the whole auto-install) ends;
          # and nothing starts it at boot (reqs §2.7).
          installer-sshd-start =
            let
              check = format:
                let
                  sshd = (mkBootConfiguration { inherit format; }).config.systemd.services.sshd;
                  ok = !(builtins.elem "pre-nixos.service" sshd.after)
                    && sshd.wantedBy == [ ] && sshd.requiredBy == [ ];
                in
                pkgs.lib.assertMsg ok
                  "${format}: sshd after=${builtins.toJSON sshd.after} wantedBy=${builtins.toJSON sshd.wantedBy}";
            in
            assert check "iso" && check "sd";
            pkgs.runCommand "installer-sshd-start" {} ''
              touch $out
            '';
          # R-P2 (amended for R-C2): the stock boot chain and set of consoles;
          # serial primary only appends the serial console once more.
          stock-aarch64-boot-settings =
            let
              stock = bootSettings stockAarch64Config.config;
              withConsole = primaryConsole: bootSettings (mkBootConfigurationWith {
                format = "sd";
                settings = { rootKey = null; autoInstall = false; inherit primaryConsole; };
              }).config;
              serialStock = stock // { kernelParams = stock.kernelParams ++ [ "console=${aarch64Config.config.services.pre-nixos.serialConsole}" ]; };
              ours = bootSettings aarch64Config.config;
            in
            assert pkgs.lib.assertMsg (withConsole "display" == stock && withConsole "serial" == serialStock && ours == serialStock)
              "pre-nixos changes the stock AArch64 boot settings beyond R-C2 (R-P2): ours=${builtins.toJSON ours} stock=${builtins.toJSON stock}";
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
