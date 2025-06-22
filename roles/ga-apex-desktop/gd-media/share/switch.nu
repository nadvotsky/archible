#!/usr/bin/env nu

#
# This is a simple script that allows to remove the snd_hda_intel kernel module.
#
# It is mainly useful for testing various module parameters, such as `model`,
#  `position_fix`, `enable_msi`, and others, without the need to reboot the
#  machine.
#
# Note that under usual conditions, the use of `rmmod snd_hda_intel`
#  is prohibited due to the devices that are using this driver.
#
# This script uses simple idea:
#  1) it performs driver unbinding for devices that are listed in the
#     `DEV_UNBIND` variable, so the driver is no longer paired with them.
#     Device is still visible to the system, and the next driver reload
#     will bind them automatically.
#  2) it calls `remove` for all devices that are not meant to be utilized
#     any further (i.e. not listed in the `DEV_UNBIND` variable), so the driver
#     will be able to be unloaded.
#     Device is completely removed from the sysfs and kernel.
#     Particulary useful for NVIDIA cards with HDMI Audio.
#
# The practical use case is the following:
#  1) Edit `DEV_UNBIND` to match required sound card.
#  2) Run `sudo nu switch.nu`
#  3) Run `modprobe snd_hda_intel position_fix=1`
#  4) Repeat as many times as needed
#
# More info:
#  unbind: https://lwn.net/Articles/143397/
#  remove: https://www.kernel.org/doc/Documentation/filesystems/sysfs-pci.txt
#

const DEV_UNBIND = [
    {device: 0x4383, vendor: 0x1002}
]

const SND_BASE = "/sys/bus/pci/drivers/snd_hda_intel"
const PCI_BASE = "/sys/bus/pci/devices"

let devs = ls $SND_BASE --short-names
    | where name =~ ":"
    | each {|dev|
        let dev_struct = $DEV_UNBIND
            | columns
            | reduce --fold {} {|prop, acc|
                let $value = open -r ($SND_BASE | path join $dev.name $prop)
                    | decode utf-8
                    | str trim
                    | into int
                $acc | upsert $prop $value
            }

        {
            action: (if $dev_struct in $DEV_UNBIND { "unbind" } else { "remove" }),
            path: ($PCI_BASE | path join $dev.name),
            bus: $dev.name,
        }
    }

print $devs

$devs
    | where action == remove
    | each {|dev|
        print $"Removing ($dev.path)"
        '1' | save -f ($dev.path | path join "remove")
    }

$devs
    | where action == unbind
    | each {|dev|
        print $"Unbinding ($dev.path)"
        $dev.bus | save -f ($SND_BASE | path join "unbind")
    }

print "Removing snd_hda_intel module"
^rmmod snd_hda_intel

print "Ensuring no alsa cards are available"
^aplay -l
^arecord -l
