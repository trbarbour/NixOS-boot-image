# Storage controller drivers the x86 image's initrd carries beyond NixOS's
# all-hardware list, whose SCSI part is "incomplete" (task queue item 48;
# reqs R-S6; #344).  Without them a controller's disks appear only once the
# real root's udev loads the driver: on the user's PC an LSI SAS1068E disk
# appeared at 67.8 s instead of about 15 s.  The modules are loaded only when
# udev finds matching hardware.  Each exists in the pinned kernel (checked
# 2026-11-11); the flake check initrd-storage-drivers keeps them in the initrd.
[
  "mptsas" # LSI SAS1064/1068 (Fusion-MPT SAS), the user's HBA
  "mpt3sas" # LSI/Broadcom SAS2008 and later (SAS2/SAS3 HBAs)
  "megaraid_sas" # LSI/Broadcom MegaRAID SAS
  "aacraid" # Adaptec/Microsemi RAID
  "smartpqi" # Microsemi/HPE Smart Array (newer than hpsa)
  "isci" # Intel C600 SAS
  "mvsas" # Marvell 88SE64xx/94xx SAS
  "pm80xx" # PMC-Sierra 8001/80xx SAS
]
