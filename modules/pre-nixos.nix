{ config, lib, pkgs, ... }:
let
  cfg = config.services.pre-nixos;
  autoInstallFlag = builtins.getEnv "PRE_NIXOS_AUTO_INSTALL";
  autoInstallEnabled = autoInstallFlag != "";
  rootKeyEnv = builtins.getEnv "PRE_NIXOS_ROOT_KEY";
  rootKeyFromEnv =
    if rootKeyEnv != "" then
      let candidate = builtins.toString rootKeyEnv; in
      if builtins.pathExists candidate then candidate else null
    else
      null;
  rootKeyCandidate =
    if rootKeyFromEnv != null then
      rootKeyFromEnv
    else
      let candidate = ../pre_nixos/root_key.pub; in
      if builtins.pathExists candidate then candidate else null;
  rootKeyEmbedded = rootKeyCandidate != null;
  autoInstallNotice =
    if autoInstallEnabled then
      "Automatic installation is enabled; pre-nixos will provision NixOS and reboot into the installed system when finished."
    else
      "Automatic installation is disabled; run pre-nixos to configure networking and start installation.";
  sshNotice =
    if rootKeyEmbedded then
      ''
      SSH access:
        - Use the matching private key for the embedded root SSH key to log in as root.
        - Add additional public keys to /root/.ssh/authorized_keys if needed.
      ''
    else
      ''
      SSH access:
        - No root SSH key is embedded in this image.
        - Set a root password with passwd or add your public key to /root/.ssh/authorized_keys before enabling remote logins.
      '';
  # ``pre-nixos`` only executes disk and network commands when PRE_NIXOS_EXEC is
  # set.  Propagate it to login shells for the TUI and to the systemd unit so the
  # boot-time invocation can configure networking.  ``disko`` relies on
  # ``nixpkgs`` being available on ``$NIX_PATH`` when executing the generated
  # configuration, so expose the evaluated nixpkgs path alongside the execution
  # flag.
  preNixosExecEnv = {
    PRE_NIXOS_EXEC = "1";
    PRE_NIXOS_NIXPKGS = "${pkgs.path}";
    PRE_NIXOS_STATE_DIR = "/run/pre-nixos";
  }
  // lib.optionalAttrs cfg.enable {
    PRE_NIXOS_VERSION = pkgs.pre-nixos.version;
  }
  // lib.optionalAttrs (autoInstallFlag != "") {
    PRE_NIXOS_AUTO_INSTALL = autoInstallFlag;
  };
  preNixosServiceEnv = preNixosExecEnv // {
    NIX_PATH = "nixpkgs=${pkgs.path}";
  };
  preNixosLoginNotice = builtins.readFile ./pre-nixos/login-notice.sh;
  preNixosServiceScript = import ./pre-nixos/service-script.nix { inherit pkgs; };
in {
  options.services.pre-nixos.enable = lib.mkEnableOption "run pre-nixos planning tool";

  config = lib.mkIf cfg.enable {
    environment.systemPackages = [
      pkgs.pre-nixos
      pkgs.disko
      pkgs.util-linux
      pkgs.minicom
      pkgs.nixos-install-tools
      pkgs.nix
    ];
    environment.sessionVariables = lib.mkMerge [
      preNixosExecEnv
      { NIX_PATH = lib.mkForce "nixpkgs=${pkgs.path}"; }
    ];
    environment.interactiveShellInit = preNixosLoginNotice;
    environment.etc."issue".text = lib.mkForce ''
      <<< Welcome to the pre-nixos auto-install boot image (${config.system.nixos.label}, \m) - \l >>>
      ${autoInstallNotice}
      (PRE_NIXOS_AUTO_INSTALL=${autoInstallFlag})
      The "nixos" and "root" accounts have empty passwords for console logins.

      ${sshNotice}

      Networking starts automatically; verify connectivity with ip addr or networkctl.

      Run "nixos-help" for the NixOS manual.
    '';
    systemd.network.enable = true;
    networking.useNetworkd = lib.mkForce true;
    networking.useDHCP = lib.mkForce false;
    networking.networkmanager.enable = lib.mkForce false;
    boot.kernelParams = [ "console=tty0" "console=ttyS0,115200n8" ];
    boot.loader.grub.memtest86.enable = true;
    boot.loader.grub.extraConfig = ''
      serial --speed=115200 --unit=0 --word=8 --parity=no --stop=1
      terminal_input serial console
      terminal_output serial console
    '';
    systemd.services.pre-nixos = {
      description = "Pre-NixOS setup";
      wantedBy = [ "multi-user.target" ];
      serviceConfig.Type = "oneshot";
      environment = preNixosServiceEnv;
      path = with pkgs; [
        coreutils
        disko
        dosfstools
        e2fsprogs
        ethtool
        gptfdisk
        iproute2
        lvm2
        mdadm
        nix
        nixos-install-tools
        parted
        systemd
        util-linux
      ];
      script = preNixosServiceScript;
    };

    # Keep OpenSSH disabled until secure_ssh hardens the configuration.
    # ``wantedBy = []`` ensures no other units pull ``sshd`` in automatically,
    # so only ``secure_ssh`` queues the non-blocking restart once the config is safe.
    services.openssh.enable = true;
    systemd.services.sshd.wantedBy = lib.mkForce [ ];
    systemd.services.sshd.after = [ "pre-nixos.service" ];
    systemd.services.sshd.serviceConfig.ExecStart =
      lib.mkForce "${pkgs.openssh}/bin/sshd -D -e -f /etc/ssh/sshd_config";
  };
}
