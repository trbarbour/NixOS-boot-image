{
  description = "Pre-NixOS setup tool";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-24.05";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils, ... }:
    let
      rootPubPath = "${builtins.toString ./.}/pre_nixos/root_ed25519.pub";
      rootPub =
        if builtins.pathExists rootPubPath then
          builtins.path { path = builtins.toPath rootPubPath; }
        else
          null;
    in
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; };
        pre-nixos = pkgs.python3Packages.buildPythonApplication {
          pname = "pre-nixos";
          version = "0.1.0";
          src = ./.;
          pyproject = true;
          nativeBuildInputs = with pkgs.python3Packages; [ setuptools wheel ];
          propagatedBuildInputs = with pkgs; [ gptfdisk mdadm lvm2 ethtool ];
          postPatch = pkgs.lib.optionalString (rootPub != null) ''
            cp ${rootPub} pre_nixos/root_ed25519.pub
          '';
        };
      in {
        packages =
          if system == "x86_64-linux" then {
            default = self.nixosConfigurations.pre-installer.config.system.build.isoImage;
            bootImage = self.nixosConfigurations.pre-installer.config.system.build.isoImage;
            pre-nixos = pre-nixos;
          } else {
            default = pre-nixos;
            pre-nixos = pre-nixos;
          };
        devShells.default = pkgs.mkShell {
          buildInputs = [ pkgs.python3 pkgs.python3Packages.pytest ];
        };
      }) // {
        nixosModules.pre-nixos = import ./modules/pre-nixos.nix;
        nixosConfigurations.pre-installer = nixpkgs.lib.nixosSystem {
          system = "x86_64-linux";
          modules = [
            ({ ... }: {
              nixpkgs.overlays = [
                (final: prev: { pre-nixos = self.packages.x86_64-linux.pre-nixos; })
              ];
            })
            self.nixosModules.pre-nixos
            "${nixpkgs}/nixos/modules/installer/cd-dvd/iso-image.nix"
            "${nixpkgs}/nixos/modules/installer/cd-dvd/installation-cd-minimal.nix"
            ({ config, ... }: { services.pre-nixos.enable = true; })
          ];
        };
      };
}
