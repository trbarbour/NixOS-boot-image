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
{ ubootRaspberryPi4_64bit }:

ubootRaspberryPi4_64bit.overrideAttrs (old: {
  pname = "uboot-rpi_4-nvme";
  extraConfig = (old.extraConfig or "") + ''
    CONFIG_NVME_PCI=y
  '';
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
