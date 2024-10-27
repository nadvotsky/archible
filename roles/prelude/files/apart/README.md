# apart

This repository hosts a utility named **apart**. Its primary function is to
seamlessly partition disks, format them, and mount new partitions in a simple
declarative command-line interface.

## Introduction

This project addresses a common issue encountered during operating system
installations, which often involves repetitive manual disk preparation tasks.

While some users may become adept at these routine tasks through repetition,
others seek automation for efficiency and consistency.

Common workarounds include self-written shell scripts or utilizing tools like
[cloud-init](https://cloudinit.readthedocs.io/en/latest/reference/examples.html#disk-setup),
[systemd-repart](https://www.freedesktop.org/software/systemd/man/latest/systemd-repart.html),
[Ansible](https://docs.ansible.com/ansible/latest/collections/community/general/parted_module.html),
or [disko](https://github.com/nix-community/disko).
While these tools serve their purpose, they may lack certain features or be
geared towards different use cases (e.g., lack of size percentages, focus on
runtime resizing, or VM-centric design).

apart aims to provide an alternative to shell scripting by utilizing
[the ABS programming language](https://www.abs-lang.org/). ABS offers modern
programming features, making the utility more robust, maintainable,
and extensible.

> Note: ABS is a single binary with minimal dependencies (written in Go) and
> occupies only 5 MB of disk storage, making it easily downloadable on demand.

## Usage

### Prerequisites

- ABS Language:
  - Install using the official instructions from
  [ABS Quick Start](https://www.abs-lang.org/quickstart.html):
    - `bash <(curl https://www.abs-lang.org/installer.sh)`
  - Alternatively, download the binary manually to a temporary location:
    - `curl -L https://github.com/abs-lang/abs/releases/latest/download/abs-linux-arm64 --output abs`
    - `chmod +x abs`
- Install required system dependencies (likely already present on most live systems):
  - `blockdev`, `lsblk`, `mount` (from `util-linux`)
  - `mkdir` (from `coreutils`)
  - `sgdisk` (from `gptfdisk`)
  - Required filesystem `mkfs` tools:
    - `mkfs.ext4` (from `e2fsprogs`)
    - `mkfs.btrfs` (from `btrfs-progs`)
    - `mkfs.exfat` (from `exfatprogs`)
    - `mkfs.ntfs` (from `ntfs-3g`)
    - `mkfs.vfat` (from `dosfstools`)

### Running apart

1. Clone this repository.
2. Run `apart`:

```bash
abs apart.abs --help
```

## Command-Line Reference

**apart** adheres to common command-line syntax conventions. For a brief summary
of POSIX utilities as a reference, refer to
[POSIX Utility Basics](https://pubs.opengroup.org/onlinepubs/009695399/basedefs/contents.html).

In summary, the utility accepts:

- **Arguments**: Mandatory values representing the primary subject of the utility.
- **Options**: Values prefixed with a single or double hyphen, including short
  or long option name, followed by a space or equals sign, and the corresponding
  value.
  - *Examples*: `-m=/mnt/`, `--disk /dev/sda`
- **Flags**: Boolean values indicated by their presence or absence,
  prefixed with one or two hyphens.
  - *Examples*: `-dry-run`, `-e`

### Command Structure

`apart [options] <partition1> [<partition2> ...]`

### Options

Flags, being similar to options, are conventionally described in this section
alongside options.

- `-d`, `--disk <disk>`:
  - Specifies the target disk to work on.
- `-m`, `--mount <dir>`:
  - Defines the mount point prepended to partition mount paths.
    If omitted, mounting is skipped.
- `-h`, `--help`:
  - Displays a man-like help message.
- `-n`, `--dry-run`:
  - Performs a simulation without making any disk modifications. Note that the
  size of the target disk specified via `-d` or `--disk` is still retrieved
  using `blockdev`, but other external tools are not executed. Hence, block
  devices are replaced with the `/dev/null/n` pattern for visualization.
- `-e`, `--explcit`
  - Disables the automatic guessing feature. Refer to the
  [Autoguessing](#autoguesting) section for more information.
- `-s`, `--no-summary`
  - Suppresses detailed information about the created partitions.

### Partition Expression

A partition expression is a comma-separated list of partition settings in the
format `key=value`. Multiple partitions are allowed. The order represents the
order of partitions to create and format, but not mount. Available settings
include:

- `name=<name>`
  - The name of the partition (EFI partition label, *PARTLABEL*),
  and the filesystem if it was formatted by specifying the `fs` setting.
- `size=<size>`
  - The size of the partition, either as a number optionally followed by a unit
  suffix (e.g., K, M, G) or as a percentage (%) of the whole disk. If not
  specified, the remaining space of the disk is used.
- `fs=<fs>`
  - The filesystem to format the partition with. Supported filesystems include
  `fat32`, `ext4`, `f2fs`, `btrfs`, `ntfs`, and `exfat`. It also supports tuning
  some `mkfs.*` options, refer to the
  [Environmental Variables](#environmental-variables) for more details.
- `mount=<mount>`
  - The mount path of this partition, appended to the `-m/--mount` option.
- `type=<type>`
  - The EFI partition type. Supported types are:

|         Name         |                 GUID                 |
| :------------------: | :----------------------------------: |
| `esp`, `efi`, `ef00` | C12A7328-F81F-11D2-BA4B-00A0C93EC93B |
|   `linux`, `8300`    | 0FC63DAF-8483-4772-8E79-3D69D8477DE4 |
|    `root`, `8304`    | 4F68BCE3-E8CD-4DB1-96E7-FBCAF984B709 |
|    `home`, `8302`    | 933AC7E1-2EB4-4F13-B844-0E14E2AEF915 |
| `nt`, `win`, `0700`  | EBD0A0A2-B9E5-4433-87C0-68B6B72699C7 |

## Environmental Variables

- `APART_MKFS_FAT32`
- `APART_MKFS_EXT4`
- `APART_MKFS_F2FS`
- `APART_MKFS_BTRFS`
- `APART_MKFS_NTFS`
- `APART_MKFS_EXFAT`
- `APART_MKFS_{FS}`

Override default options for the `mkfs.*` family (e.g., `-O` for
[`mkfs.ext4(8)`](https://man7.org/linux/man-pages/man8/mke2fs.8.html)).

## Examples

Create a new GPT partition table on `/dev/sda` with:

- 1GB EFI partition
- root partition using the remaining space

and mount them into `/mnt`:

```bash
abs apart.abs -d /dev/sda -m /mnt type=esp,size=1G type=root
```

> By default, autoguessing assigns *FAT32* for the EFI partition and mounts it
> at `/mnt` + `/boot`. The root partition is formatted as *ext4* and mounted
> at `/mnt` + `/`. Please proceed to the [Autoguesting](#autoguesting) for more
> information.

---

Create a new GPT partition table on `/dev/nvme0n1` with:

- 300MB EFI partition
- root partition using 50% of the disk size with *BTRFS* filesystem
- shared data partition with *exFAT* filesystem for the rest of the disk size

and do not mount it:

```bash
abs apart.abs -d /dev/nvme0n1 type=esp,size=200M type=root,size=50%,fs=btrfs type=nt,fs=exfat
```

## Autoguesting

The autoguessing feature simplifies partition expressions. It never overrides
existing settings and only injects new settings when the `-e/--explicit` option
is not specified.

Autoguessing uses the following `type` mapping:

- `esp`, `efi`, `ef00`:
  - `fs=fat32`
  - `mount=/boot`
- `root`, `8304`:
  - `fs=ext4`
  - `mount=/`
- `home`, `8302`:
  - `fs=ext4`
  - `mount=/home`
- `nt`, `win`, `0700`
  - `fs=ntfs`

## Extensibility

**apart** is designed as a single-file script for ease of use and download.
The most important variables are located at the top of the script and can be
easily configured.

Before making modifications, familiarity with the basics of the ABS language
is recommended: <https://www.abs-lang.org/docs/>

For example, to add support for a new filesystem:

- Add the filesystem name to the `PART_FS_ALLOW` array.
- Add the entry to the `MKFS_OPTS` hash with the key of the added filesystem
  and the value of a function that returns the command line to execute
  (typically `mkfs.*`).

To modify the autoguessing feature functionality:

- Change the `PART_ENCHANCE_MAP` mapping.

Potential enhancements include:

- Non-x86 root partition codes (`8304`, `8305`) and the corresponding
  autodetection
- Additional filesystems (e.g., *zfs*)
