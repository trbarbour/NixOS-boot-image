# The FAT files for the installed system's /boot on a Raspberry Pi 4 / CM4
# NVMe disk (plan item 8, design D1/D2; R-B1).
#
# Runs the stock SD image's own sdImage.populateFirmwareCommands (reused, not
# copied: R-P2), then swaps in the NVMe-capable U-Boot.  Everything else is
# byte-for-byte the stock FIRMWARE partition (experiment E9).
{ runCommand, populateFirmwareCommands, ubootRpi4Nvme }:

runCommand "rpi4-nvme-firmware" { } ''
  cd "$NIX_BUILD_TOP"
  mkdir firmware
  ${populateFirmwareCommands}
  # The stock config.txt boots this file on [pi4] (which includes the CM4).
  test -f firmware/u-boot-rpi4.bin
  grep -qx "kernel=u-boot-rpi4.bin" firmware/config.txt
  cp --remove-destination ${ubootRpi4Nvme}/u-boot.bin firmware/u-boot-rpi4.bin
  cp -r firmware "$out"
''
