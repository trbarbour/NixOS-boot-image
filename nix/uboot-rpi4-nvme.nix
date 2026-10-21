# U-Boot for the installed system on a Raspberry Pi 4 / CM4 booting from NVMe
# (plan item 8, option (a'); R-B1, R-B2).
#
# nixpkgs builds ubootRaspberryPi4_64bit from plain rpi_4_defconfig, which has
# no NVMe driver and scans "mmc usb pxe dhcp" (finding E9a, 2026-10-19).  Two
# changes, nothing else, so the boot chain otherwise stays the stock one:
#   - CONFIG_NVME_PCI=y: read the NVMe disk over the CM4's PCIe (PCI_BRCMSTB
#     is already enabled);
#   - "nvme" first in boot_targets: with the SD card still inserted, boot the
#     installed system's extlinux.conf, not the card's (R-B2).
#
# Version: v2026.10, not nixpkgs' 2026.04.  On a CM4 (E9b, 2026-10-20) 2026.04
# found the PCIe link but every NVMe probe timed out ("Failed to probe
# 'nvme#0': err=-110").  2026.04..2026.10 brings the NVMe inbound-address
# translation fix (09b1c0f98c), the BCM2711 iBAR rework (585d6cfd9b,
# df883ec51b) and dma-ranges fixes (a383c96892, 53e9c41847).  Pinned by commit:
# fetched over git (the GitHub tarball API is not reachable from build
# sessions), and only when this package is built.
{ ubootRaspberryPi4_64bit }:

ubootRaspberryPi4_64bit.overrideAttrs (old: {
  pname = "uboot-rpi_4-nvme";
  version = "2026.10";
  src = builtins.fetchGit {
    url = "https://github.com/u-boot/u-boot";
    ref = "refs/tags/v2026.10";
    rev = "5508406582f6f7120dce0c4b3059819a41788db2";
    shallow = true;
  };
  extraConfig = (old.extraConfig or "") + ''
    CONFIG_NVME_PCI=y
  '';
  # E9b-3 (2026-10-20, #316): reads must be translated like admin commands.
  patches = (old.patches or [ ]) ++ [ ./patches/uboot-nvme-rw-dma-translation.patch ];
  postPatch = old.postPatch + ''
    substituteInPlace board/raspberrypi/rpi/rpi.env \
      --replace-fail "boot_targets=mmc usb pxe dhcp" "boot_targets=nvme mmc usb pxe dhcp"
  '';
  postConfigure = (old.postConfigure or "") + ''
    # Resolve the appended option now (the build would anyway), and fail the
    # build if Kconfig dropped it (e.g. an unmet dependency).
    make olddefconfig
    grep -qx "CONFIG_NVME_PCI=y" .config
    grep -qx "CONFIG_CMD_NVME=y" .config
  '';
})
