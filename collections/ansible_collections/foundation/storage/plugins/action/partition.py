#
# foundation.storage.partition - manage disk storage partition table.
#
# Follow the project README for more information.
#
import typing

import dataclasses
import collections
import operator
import string

import re
import json
import os.path
import shlex

from ansible.plugins.action import ActionBase
from ansible.errors import AnsibleActionFail
from ansible.utils.display import Display

from ansible.constants import COLOR_CHANGED, COLOR_OK

from ansible_collections.foundation.util.types import RawResult, TaskVars
from ansible_collections.foundation.util.specs import validate_spec


ARGS_SPEC = {
    "disk": dict(type="path", required=True),
    "base": dict(type="path", required=True),
}

LAYOUT_SPEC = {
    "name": dict(type="str", required=True),
    "table": {
        "type": "dict",
        "options": {
            "type": dict(type="str", required=True),
            "size": dict(type="str", required=True),
        },
        "required": True,
    },
    "fs": {
        "type": "dict",
        "options": {
            "type": dict(type="str", required=True),
            "exec": dict(type="str"),
        },
    },
    "mount": {
        "type": "dict",
        "options": {
            "path": dict(type="str", required=True),
            "mode": dict(type="str"),
            "opts": dict(type="str"),
            "exec": dict(type="str"),
        },
    },
}

VARS_SPEC = {
    "layout": {
        "type": "list",
        "elements": "dict",
        "options": LAYOUT_SPEC,
        "required": True,
    }
}


#
# A definition for well-known filesystems. Non-supported ones with no explicit templates will use generic fallback
#  cmdlines, which may not the best option (i.e. it will not set the filesystem label).
#
KNOWN_FILESYSTEMS = collections.defaultdict(
    dict,
    swap={
        "package": "util-linux",
        "format_cmd": "mkswap -L $NAME $PART",
        "mount_opts": tuple(),
        "mount_cmd": "swapon $SRC",
    },
    ext4={
        "package": "e2fsprogs",
        "format_opts": (
            "fast_commit",
            "64bit",
            "dir_index",
            "ext_attr",
            "extent",
            "filetype",
            "flex_bg",
            "has_journal",
            "inline_data",
            "large_dir",
            "large_file",
            "sparse_super",
            "metadata_csum",
        ),
        "format_cmd": "mkfs.ext4 -F -L $NAME -t $FS -O $OPTS $PART",
    },
    btrfs={
        "package": "btrfs-progs",
        "format_opts": (
            "extref",
            "skinny-metadata",
            "no-holes",
        ),
        "format_cmd": "mkfs.btrfs -f -L $NAME -O $OPTS $PART",
    },
    xfs={
        "package": "xfsprogs",
        "format_cmd": "mkfs.xfs -f -L $NAME -f $PART",
        "mount_opts": (
            "nodiscard",
            "noquota",
        ),
    },
    f2fs={
        "package": "f2fs-tools",
        "format_opts": (
            "extra_attr",
            "flexible_inline_xattr",
            "inode_checksum",
        ),
        "format_cmd": "mkfs.f2fs -f -i -l $NAME -O $OPTS $PART",
    },
    vfat={
        "package": "dosfstools",
        "format_cmd": "mkfs.vfat -F 32 -n $NAME $PART",
        "mount_opts": (
            "errors=remount-ro",
            "check=strict",
            "tz=UTC",
            "dmask=0027",
            "fmask=0037",
        ),
    },
    exfat={
        "package": "exfatprogs",
        "format_cmd": "mkfs.exfat -L $NAME $PART",
    },
    ntfs={
        "package": "ntfs-3g",
        "format_cmd": "mkfs.ntfs -Q -L $NAME $PART",
        "mount_cmd": "mount -t ntfs3 -o $OPTS $SRC $DST",
    },
)


class ModuleExecutor:
    def __init__(self, action: ActionBase, task_vars: TaskVars):
        self._action = action
        self._display = action._display
        self._check_mode = action._task.check_mode
        self._task_vars = task_vars

    def stat(self, path: str) -> RawResult:
        #
        # ansible.builtin.stat is not affected by check mode, no need for additional workarounds.
        #
        result = self._action._execute_module(
            module_name="ansible.builtin.stat",
            module_args=dict(path=path, follow=True, get_checksum=False, get_mime=False),
            task_vars=self._task_vars,
        )
        if result.get("failed") is True:
            raise AnsibleActionFail("Cannot stat '{}': {}".format(path, result))

        return result["stat"]

    def mkdir(self, path: str, mode: str, owner: str, group: str) -> None:
        #
        # Closure class allows to omit passing too many arguments in a handy OOP way.
        #
        class ModuleExecutorDirectory:
            @staticmethod
            def run_as_unsafe(report: str | None = None) -> None:
                if self._check_mode is True:
                    return report and self._display.display(report, COLOR_OK)

                result = self._action._execute_module(
                    module_name="ansible.builtin.file",
                    module_args=dict(path=path, state="directory", recurse=True, mode=mode, owner=owner, group=group),
                    task_vars=self._task_vars,
                )
                if result.get("failed") is True:
                    raise AnsibleActionFail("Cannot create directory '{}': {}".format(path, result))

                report and self._display.display(report, COLOR_CHANGED)

        return ModuleExecutorDirectory()

    def _force_run_command(self, argv: collections.abc.Sequence[str]) -> RawResult:
        #
        # In order to force _execute_module to complete ansible.builtin.command regardless of the check mode,
        #  the check_mode of the current action task needs to be set to False.
        #
        # Passing the _ansible_check_mode as the module argument does nothing; it always gets overwritten.
        #
        self._action._task.check_mode = False
        try:
            result = self._action._execute_module(
                module_name="ansible.builtin.command",
                module_args=dict(argv=argv),
                task_vars=self._task_vars,
            )
            return result.get("failed") is True or result.get("rc") != 0, result
        finally:
            self._action._task.check_mode = self._check_mode

    def _do_command(self, package: str, binary: str, args: collections.abc.Sequence[str]) -> str:
        failed, result = self._force_run_command([binary, *args])
        if not failed:
            return result["stdout"]

        failed, whereis = self._force_run_command(["whereis", "-b", binary])
        if failed:
            self._display.warning(
                "Unable to debug '{}' failure with whereis. Is util-linux installed?".format(binary),
            )
        elif len(whereis["stdout"].strip().split(": ")) == 1:
            raise AnsibleActionFail(
                "Command '{}' was not found. Ensure the '{}' package is installed".format(binary, package),
            )

        raise AnsibleActionFail("Failed to run '{}' ({}): {}".format(binary, args, result))

    def lsblk(self, disk: str, fields: collections.abc.Sequence[str]) -> tuple[dict, list[dict]]:
        stdout = self._do_command("util-linux", "lsblk", ["-J", "-o", ",".join(fields), disk])
        canonical, *blockdevices = json.loads(stdout)["blockdevices"]

        return canonical, blockdevices

    def command(self, package: str, binary: str, args: collections.abc.Sequence[str]):
        #
        # Closure class allows to omit passing too many arguments in a handy OOP way.
        #
        class ModuleExecutorCommand:
            @classmethod
            def _print_report(cls, report: str, changed: bool) -> None:
                self._display.display(report, COLOR_CHANGED if changed else COLOR_OK)

            #
            # Execute the provided command even when running in the check mode.
            #
            @classmethod
            def run_as_safe(cls, report: str | None = None) -> str:
                stdout = self._do_command(package, binary, args)

                report and cls._print_report(report, changed=False)

                return stdout

            #
            # Execute the provided command if not running in the check mode. Only print a message otherwise.
            #
            @classmethod
            def run_as_unsafe(cls, report: str | None = None) -> str:
                stdout = "" if self._check_mode else self._do_command(package, binary, args)

                report and cls._print_report(report, changed=not self._check_mode)

                return stdout

        return ModuleExecutorCommand()


#
# This action plugin operates within a complex invocation context. Throughout the plugin’s lifecycle, it is important
#  to maintain reliable representation and validation of input data. Typical implementations may use one of
#  the following approaches:
#   1) A dataclass with a __post_init__ method for post-initialization validation.
#   2) A regular class with setters implementing custom validation logic.
#   3) An external library such as attrs, pydantic, or similar.
#   4) A builder class that uses guard flags to prevent incomplete initialization.
#   5) A step builder pattern that uses multiple classes, each responsible for initializing a specific field.
#
# In this codebase, models follow the step builder pattern. Although this approach introduces a significant amount
#  of boilerplate, it offers an interesting design: strict initialization guarantees enforced by the type system rather
#  than relying solely on runtime checks.
#


@dataclasses.dataclass(frozen=True)
class DeviceFrontage:
    disk: str
    sector_size: int
    sectors: int


class DeviceFinalBuilder:
    def __init__(self, modexec: ModuleExecutor, disk: str):
        self._modexec = modexec
        self._disk = disk

    def build(self) -> DeviceFrontage:
        blockdev = self._modexec.command("util-linux", "blockdev", ["--getss", "--getsize64", self._disk])
        sector, size = map(int, blockdev.run_as_safe().split())

        return DeviceFrontage(disk=self._disk, sector_size=sector, sectors=int(size / sector) - 1)


class DeviceBuilder:
    def __init__(self, display: Display, modexec: ModuleExecutor):
        self._display = display
        self._modexec = modexec

    def with_disk(self, disk: str) -> DeviceFinalBuilder:
        exists, isblk, isreg = map(self._modexec.stat(disk).get, ("exists", "isblk", "isreg"))

        if exists is False:
            raise AnsibleActionFail("Disk '{}' does not exist".format(disk))
        elif isblk is False and isreg is False:
            raise AnsibleActionFail("Disk '{}' must represent a block device or a file".format(disk))
        elif isblk is False:
            self._display.warning("Disk '{}' does not point to a block device, this may be a typo".format(disk))

        #
        # List any mountpoints or swaps linked to the disk.
        #
        _, blockdevices = self._modexec.lsblk(disk, ("PATH", "MOUNTPOINT"))
        mounts = [
            "{} ({})".format(dev["path"], dev["mountpoint"]) for dev in blockdevices if dev["mountpoint"] is not None
        ]
        if not len(mounts):
            pass
        elif self._modexec._check_mode is True:
            self._display.warning("Check mode allows the disk '{}' to be used: '{}'".format(disk, ", ".join(mounts)))
        else:
            raise AnsibleActionFail("Disk '{}' is still being used: '{}'".format(disk, ", ".join(mounts)))

        return DeviceFinalBuilder(self._modexec, disk)


@dataclasses.dataclass(frozen=True)
class TableFrontage:
    #
    # GPT Partition Type. It is a direct mapping to the gptfdisk interface, which supports:
    #   1) Raw GUID expression, such as C12A7328-F81F-11D2-BA4B-00A0C93EC93B.
    #   2) Short gptfdisk type such as ef00. See https://github.com/samangh/gptfdisk/blob/master/parttypes.cc.
    #
    type: str
    #
    # Size of the partition. Can be represented in one of the following ways:
    #  1) -1   => filler partition, occupy as much of free space as possible.
    #  2) 0..1 => fraction of the disk size.
    #  3) 1... => partition size in bytes.
    #
    size: float


class TableFinalBuilder:
    def __init__(self, type: str, size: int):
        self._type = type
        self._size = size

    def build(self) -> TableFrontage:
        return TableFrontage(self._type, self._size)


class TableSizeBuilder:
    UNITS = {
        "K": 1024,
        "KB": 1000,
        "M": 1024**2,
        "MB": 1000**2,
        "G": 1024**3,
        "GB": 1000**3,
        "T": 1024**4,
        "TB": 1000**4,
    }

    def __init__(self, type: str):
        self._type = type

    def with_size(self, value: str) -> TableFinalBuilder:
        if value == "auto":
            return TableFinalBuilder(self._type, -1)

        if value.endswith("%"):
            suffix, multiplier = "%", (1 / 100)
        else:
            suffix, multiplier = next(
                ((unit, mult) for unit, mult in self.UNITS.items() if value.endswith(unit)),
                ("", 1),
            )

        base = value.removesuffix(suffix)
        if not base.isdigit():
            raise AnsibleActionFail("Failed to parse size expression '{}': non-numeric base".format(value))

        size = int(base)
        if size <= 0:
            raise AnsibleActionFail("Failed to process size literal '{}': negative or zero size".format(value))
        elif suffix == "%" and size > 100:
            raise AnsibleActionFail("Failed to parse size percentage '{}': bigger than 100".format(value))

        return TableFinalBuilder(self._type, size * multiplier)


class TableBuilder:
    #
    # Refer to the TableFrontage for more info.
    #
    ALIASES = {
        "efi": "ef00",
        "esp": "ef00",
        "xbootldr": "ea00",
        "swap": "8200",
        "linux": "8300",
        "home": "8302",
        "root": "8304",
        "root-x86": "8303",
        "root-x86_64": "8304",
        "root-arm64": "8305",
        "root-arm32": "8307",
        "root-ia64": "830a",
        "nt": "0700",
        "win": "0700",
        "windows": "0700",
    }

    def with_type(self, value: str):
        if value in self.ALIASES:
            return TableSizeBuilder(self.ALIASES[value])

        if not set(value.replace("-", "")).issubset(string.hexdigits):
            raise AnsibleActionFail("Manual partition type '{}' must be hexadecimal".format(value))

        match tuple(i for i in range(len(value)) if value[i] == "-"):
            case () if len(value) != 4:
                raise AnsibleActionFail("Short partition type '{}' must be of 4 hex digits".format(value))

            case (8, 13, 18, 23) if len(value) != 32:
                raise AnsibleActionFail("Raw GUID partition type expression '{}' is invalid".format(value))

            case () | (8, 13, 18, 23):
                return TableSizeBuilder(value)

            case _:
                raise AnsibleActionFail("Cannot parse partition type '{}'".format(value))


@dataclasses.dataclass(frozen=True)
class FileSystemFrontage:
    name: str
    cmd: str
    opts: str

    def evaluate(self, name: str, partition: str) -> str:
        return string.Template(self.cmd).safe_substitute(
            PART=shlex.quote(partition),
            NAME=shlex.quote(name),
            FS=self.name,
            OPTS=self.opts,
        )


class FileSystemFinalBuilder:
    def __init__(self, name: str, cmd: str, opts: str):
        self._name = name
        self._cmd = cmd
        self._opts = opts

    def build(self) -> FileSystemFrontage:
        return FileSystemFrontage(self._name, self._cmd, self._opts)


class FileSystemCmdBuilder:
    DEFAULT_FALLBACK_CMD = "mkfs.$FS $PART"

    def __init__(self, display: Display, name: str):
        self._display = display
        self._name = name
        self._opts = ",".join(KNOWN_FILESYSTEMS[self._name].get("format_opts", tuple()))

    def with_cmd(self, cmd: str) -> FileSystemFinalBuilder:
        return FileSystemFinalBuilder(self._name, cmd, self._opts)

    def without_cmd(self) -> FileSystemFinalBuilder:
        if (format_cmd := KNOWN_FILESYSTEMS[self._name].get("format_cmd")) is not None:
            return FileSystemFinalBuilder(self._name, format_cmd, self._opts)
        else:
            self._display.warning(
                "Unknown filesystem '{}' with no explicit command template. Using fallback '{}'".format(
                    self._name,
                    self.DEFAULT_FALLBACK_CMD,
                ),
            )

        return FileSystemFinalBuilder(self._name, self.DEFAULT_FALLBACK_CMD, self._opts)


class FileSystemBuilder:
    def __init__(self, display: Display):
        self._display = display

    def with_name(self, name: str) -> FileSystemCmdBuilder:
        return FileSystemCmdBuilder(self._display, name)


@dataclasses.dataclass(frozen=True)
class MountFrontage:
    #
    # Mount point without base. May be None in the pathless cases (for instance, swap partitions).
    #
    path: str | None
    #
    # Mount point permissions in the following form: (mod, owner, group).
    #
    access: tuple[str, str, str]
    opts: str
    cmd: str

    def evaluate(self, base: str, partition: str) -> str:
        return string.Template(self.cmd).safe_substitute(
            SRC=shlex.quote(partition),
            DST=(shlex.quote(os.path.normpath(base + self.path)) if self.path is not None else '""'),
            OPTS=self.opts,
        )


class MountFinalBuilder:
    def __init__(self, path: str | None, access: tuple[str, str, str], opts: str, cmd: str):
        self._path = path
        self._access = access
        self._opts = opts
        self._cmd = cmd

    def build(self) -> MountFrontage:
        return MountFrontage(self._path, self._access, self._opts, self._cmd)


class MountCmdBuilder:
    DEFAULT_FALLBACK_CMD = "mount -o $OPTS $SRC $DST"

    def __init__(self, fs: str | None, path: str, access: tuple[str, str, str], opts: str):
        self._fs = fs
        self._path = path
        self._access = access
        self._opts = opts

    def with_cmd(self, cmd: str) -> MountFinalBuilder:
        return MountFinalBuilder(self._path, self._access, self._opts, cmd)

    def without_cmd(self) -> MountFinalBuilder:
        return MountFinalBuilder(
            self._path,
            self._access,
            self._opts,
            KNOWN_FILESYSTEMS[self._fs].get("mount_cmd", self.DEFAULT_FALLBACK_CMD),
        )


class MountOptsBuilder:
    DEFAULT_OPTS = "async,noatime,auto,dev,exec,noiversion,suid,rw,nouser"

    def __init__(self, fs: str | None, path: str, access: tuple[str, str, str]):
        self._fs = fs
        self._path = path
        self._access = access

        match KNOWN_FILESYSTEMS[self._fs].get("mount_opts"):
            #
            # For unknown systems, assume it supports generic options.
            #
            case None:
                self._defaults = self.DEFAULT_OPTS

            #
            # Do not prepend anything for an empty tuple. This is useful for special cases such as swap.
            #
            case ():
                self._defaults = "defaults"

            #
            # Prepend advanced 'defaults' replacement.
            #
            case valid_sequence:
                self._defaults = ",".join((self.DEFAULT_OPTS, *valid_sequence))

    def with_opts(self, opts: str) -> MountCmdBuilder:
        return MountCmdBuilder(
            self._fs,
            self._path,
            self._access,
            #
            # Render user-specified options as a template. This unlocks performing light modifications
            #  (for example, appending '$OPTS,errors=remount-ro').
            #
            string.Template(opts).safe_substitute(OPTS=self._defaults),
        )

    def without_opts(self) -> MountCmdBuilder:
        return MountCmdBuilder(self._fs, self._path, self._access, self._defaults)


class MountAccessBuilder:
    def __init__(self, fs: str | None, path: str):
        self._fs = fs
        self._path = path

    def with_access(self, expression: str) -> MountOptsBuilder:
        match = re.match(r"^(\d{3}):(\w+):(\w+)$", expression)
        if match is None:
            raise AnsibleActionFail(
                "Cannot parse permission expression '{}': must be 'mod:owner:group'".format(expression),
            )

        return MountOptsBuilder(self._fs, self._path, tuple(match.groups()))

    def without_access(self) -> MountOptsBuilder:
        #
        # Something reasonable for default permissions, as partitioning is generally to be done by superuser.
        #
        return MountOptsBuilder(self._fs, self._path, ("755", "root", "root"))


class MountBuilder:
    def __init__(self, fs: str):
        self._fs = fs

    def with_path(self, path: str) -> MountAccessBuilder:
        if path == "none" and self._fs == "swap":
            #
            # Swap has no mount destination.
            #
            return MountAccessBuilder(self._fs, None)
        elif path == "none":
            raise AnsibleActionFail("Invalid path 'none' for non-swap partitions")

        if not os.path.isabs(path):
            raise AnsibleActionFail("Expected mount path '{}' to be absolute".format(path))

        return MountAccessBuilder(self._fs, os.path.normpath(path))


@dataclasses.dataclass(frozen=True)
class PartitionFrontage:
    name: str

    table: TableFrontage
    fs: FileSystemFrontage | None
    mount: MountFrontage | None


class PartitionBuilder:
    def __init__(self, display: Display):
        self._display = display

    def _build_name(self, name: str) -> str:
        if not name:
            raise AnsibleActionFail("Empty partition name is prohibited")

        if len(name) > 10:
            self._display.warning("It is recommended for the partition name '{}' to be 1-10 chars long".format(name))

        if re.search(r"[^\w\-_]", name) is not None:
            self._display.warning(
                "Consider removing special symbols and spaces from the partition name '{}'".format(name),
            )

        return name

    def _build_table(self, table_composite: dict) -> TableFrontage:
        builder = TableBuilder()

        builder = builder.with_type(table_composite["type"])
        builder = builder.with_size(table_composite["size"])

        return builder.build()

    def _build_fs(self, fs_composite: dict | None) -> FileSystemFrontage | None:
        if fs_composite is None:
            return None

        name, cmd = fs_composite["type"], fs_composite["exec"]
        builder = FileSystemBuilder(self._display)

        builder = builder.with_name(name)
        builder = builder.without_cmd() if cmd is None else builder.with_cmd(cmd)

        return builder.build()

    def _build_mount(self, fs_name: str, mount_composite: dict | None) -> MountFrontage | None:
        if mount_composite is None:
            return None

        path, mode, opts, cmd = (mount_composite[prop] for prop in ("path", "mode", "opts", "exec"))
        builder = MountBuilder(fs_name)

        builder = builder.with_path(path)
        builder = builder.without_access() if mode is None else builder.with_access(mode)
        builder = builder.without_opts() if opts is None else builder.with_opts(opts)
        builder = builder.without_cmd() if cmd is None else builder.with_cmd(cmd)

        return builder.build()

    def from_composite(self, composite: dict) -> PartitionFrontage:
        return PartitionFrontage(
            name=self._build_name(composite["name"]),
            table=self._build_table(composite["table"]),
            fs=self._build_fs(composite["fs"]),
            mount=self._build_mount(
                #
                # This is a hint for the builder, not the actual filesystem. Can be an empty string or None.
                #
                "auto" if composite["fs"] is None else composite["fs"]["type"],
                composite["mount"],
            ),
        )


@dataclasses.dataclass(frozen=True)
class LayoutFrontage:
    base: str
    frontages: tuple[PartitionFrontage]


class LayoutFinalBuilder:
    def __init__(self, base: str, frontages: tuple[PartitionFrontage]):
        self._base = base
        self._frontages = frontages

    def build(self) -> LayoutFrontage:
        return LayoutFrontage(self._base, self._frontages)


class LayoutPartitionsBuilder:
    def __init__(self, display: Display, base: str):
        self._builder = PartitionBuilder(display)
        self._base = base

    def with_partitions(self, partitions: collections.abc.Iterable[dict]) -> LayoutFinalBuilder:
        models = tuple((self._builder.from_composite(composite) for composite in partitions))
        if sum((1 for model in models if model.table.size == -1)) > 1:
            raise AnsibleActionFail("More than one partition with size=auto filler")

        return LayoutFinalBuilder(self._base, models)


class LayoutBuilder:
    def __init__(self, display: Display, modexec: ModuleExecutor):
        self._display = display
        self._modexec = modexec

    def with_base(self, base: str) -> LayoutPartitionsBuilder:
        if not os.path.isabs(base):
            raise AnsibleActionFail("Base path '{}' must be absolute".format(base))

        stat = self._modexec.stat(base)
        if stat["exists"] is False:
            raise AnsibleActionFail("Base path '{}' does not exist".format(base))
        elif stat["isdir"] is False:
            raise AnsibleActionFail("Base path '{}' must be the existent directory".format(base))

        return LayoutPartitionsBuilder(self._display, os.path.normpath(base))


class ArrangementStage:
    GPT_ENTRY_ARRAY_SIZE = 16_384
    ALIGN_DEFAULT = 2048
    ALIGN_UNUSUAL = 1024

    def __init__(self, display: Display, modexec: ModuleExecutor, device: DeviceFrontage, layout: LayoutFrontage):
        self._display = display
        self._modexec = modexec
        self._device = device
        self._layout = layout

    #
    # Build device sector layout. Follow the https://en.wikipedia.org/wiki/GUID_Partition_Table for more information.
    #
    def _build_map(self) -> tuple[list[str, int], list[str, int], list[str, int]]:
        entries = int(self.GPT_ENTRY_ARRAY_SIZE / self._device.sector_size)
        align = self.ALIGN_DEFAULT if self._device.sector_size == 512 else self.ALIGN_UNUSUAL

        upper = [("Protective MBR", 1), ("Primary GPT Header", 1), ("Primary GPT Entries", entries)]
        upper.append(("Primary Alignment", align - sum(map(operator.itemgetter(1), upper))))

        lower = [("Secondary GPT Entries", entries), ("Secondary GPT Header", 1)]
        lower.insert(0, ("Secondary Alignment", align - sum(map(operator.itemgetter(1), lower))))

        middle, available = [], self._device.sectors - sum(map(operator.itemgetter(1), upper + lower))
        for frontage in self._layout.frontages:
            if frontage.table.size <= -1:
                occupies = -1
            elif frontage.table.size <= 1.0:
                occupies = int(round(self._device.sectors * frontage.table.size))
            else:
                occupies = int(round(frontage.table.size / self._device.sector_size))

            middle.append((frontage.name, occupies))

            available -= occupies
            if available < 0:
                raise AnsibleActionFail("Size overflow of device partition table: '{}'".format(frontage))

        if (filler := next((index for index in range(len(middle)) if middle[index][1] <= -1), None)) is not None:
            middle[filler] = (middle[filler][0], available)
        else:
            middle.append(("Free Space", available))

        return upper, middle, lower

    @staticmethod
    def _humanize(num: int) -> str:
        for unit in ("B", "KiB", "MiB", "GiB"):
            if abs(num) < 1024:
                return f"{num:.2f} {unit}"

            num /= 1024
        else:
            return f"{num:.2f} TiB"

    def run(self) -> None:
        upper, middle, lower = self._build_map()
        for name, occupies in upper + middle + lower:
            self._display.display(
                "partition: ({}) => '{} sector(s), {}'".format(
                    name,
                    occupies,
                    self._humanize(occupies * self._device.sector_size),
                ),
                COLOR_OK,
            )

        #
        # Use --zap-all in order to destroy any possible existing MBR that may cause gptfdisk to refuse to proceed.
        #
        cmdline, sector = ["--zap-all", "--clear"], sum(map(operator.itemgetter(1), upper))
        for (name, occupies), frontage in zip(middle, self._layout.frontages):
            #
            # LBA starts with 0, do not forget to subtract 1.
            #
            cmdline.append("-n")
            cmdline.append(f"0:{sector}:{sector + occupies - 1}")

            cmdline.append("-t")
            cmdline.append(f"0:{frontage.table.type}")

            cmdline.append("-c")
            cmdline.append(f"0:{name}")

            sector += occupies

        cmdline.append(self._device.disk)

        command = self._modexec.command("gptfdisk", "sgdisk", cmdline)
        command.run_as_unsafe(report="partition: (gptfdisk) => 'sgdisk {}'".format(" ".join(cmdline)))


class FormatStage:
    def __init__(self, modexec: ModuleExecutor, device: DeviceFrontage, layout: LayoutFrontage):
        self._modexec = modexec
        self._device = device
        self._layout = layout

    def run(self, partitions: tuple[str]) -> None:
        for partition, frontage in zip(partitions, self._layout.frontages):
            if frontage.fs is None:
                continue

            cmdline = frontage.fs.evaluate(frontage.name, partition)
            mkfs, *args = shlex.split(cmdline)

            command = self._modexec.command(KNOWN_FILESYSTEMS[frontage.fs.name]["package"], mkfs, args)
            command.run_as_unsafe(report="format: ({}) => '{}'".format(frontage.name, cmdline))


class MountStage:
    def __init__(self, modexec: ModuleExecutor, device: DeviceFrontage, layout: LayoutFrontage):
        self._modexec = modexec
        self._device = device
        self._layout = layout

    def run(self, partitions: tuple[str]) -> None:
        #
        # In order to mount partitions in the correct order, they can be sorted.
        #  For instance, [/boot, /home, /] would be ordered as [/, /boot, /home].
        #
        entries = sorted(
            (
                (partition, frontage)
                for partition, frontage in zip(partitions, self._layout.frontages)
                if frontage.mount is not None
            ),
            key=lambda descriptor: descriptor[1].mount.path or "",
        )

        for partition, frontage in entries:
            if frontage.mount.path is not None:
                #
                # Use concatenation instead of the os.path.join as both paths are absolute.
                #
                path = os.path.normpath(self._layout.base + frontage.mount.path)
                mkdir = self._modexec.mkdir(path, *frontage.mount.access)
                mkdir.run_as_unsafe("mount: ({}) => '{}:{}:{}:{}'".format(frontage.name, path, *frontage.mount.access))

            cmdline = frontage.mount.evaluate(self._layout.base, partition)
            binary, *args = shlex.split(cmdline)

            command = self._modexec.command(KNOWN_FILESYSTEMS[frontage.fs.name]["package"], binary, args)
            command.run_as_unsafe(report="mount: ({}) => '{}'".format(frontage.name, cmdline))


#
# Abstract report entry that is returned upon completion.
#
class SubmissionEntry(typing.TypedDict):
    name: str
    part_path: str
    part_uuid: str
    fs_name: str | None
    mount_path: str | None
    mount_opts: str | None


#
# fstab entry that is returned upon completion. Refer to the https://man7.org/linux/man-pages/man5/fstab.5.html.
#
# It is only generated for those partitions that have both 'mount' and 'fs'.
#
class FstabEntry(typing.TypedDict):
    fs_spec: str
    fs_file: str
    fs_vfstype: str
    fs_mntops: str
    fs_freq: int
    fs_passno: int


class ActionModule(ActionBase):
    def _build_layout_frontage(self, modexec: ModuleExecutor, raw_args: dict, raw_vars: dict) -> LayoutFrontage:
        builder = LayoutBuilder(self._display, modexec)

        builder = builder.with_base(raw_args["base"])
        builder = builder.with_partitions(raw_vars["layout"])

        return builder.build()

    def _build_device_frontage(self, modexec: ModuleExecutor, raw_args: dict) -> DeviceFrontage:
        builder = DeviceBuilder(self._display, modexec)

        builder = builder.with_disk(raw_args["disk"])

        return builder.build()

    def _build_submission(
        self,
        modexec: ModuleExecutor,
        device: DeviceFrontage,
        layout: LayoutFrontage,
    ) -> tuple[SubmissionEntry]:
        canonical, blockdevices = modexec.lsblk(device.disk, ("PATH", "PARTUUID"))
        if self._task.check_mode:
            blockdevices = [
                dict(
                    path="{}/placeholder-{}".format(canonical["path"], i),
                    partuuid="00000000-0000-0000-0000-000000000000",
                )
                for i in range(len(layout.frontages))
            ]

        submission = []
        for blockdev, frontage in zip(blockdevices, layout.frontages):
            entry = SubmissionEntry(
                name=frontage.name,
                part_path=blockdev["path"],
                part_uuid=blockdev["partuuid"],
                fs_name=None,
                mount_path=None,
                mount_opts=None,
            )

            if frontage.fs is not None:
                entry["fs_name"] = frontage.fs.name

            if frontage.mount is not None:
                entry["mount_path"] = frontage.mount.path
                entry["mount_opts"] = frontage.mount.opts

            submission.append(entry)

        return tuple(submission)

    def _build_fstab(self, submission: tuple[SubmissionEntry]) -> tuple[FstabEntry]:
        fstab = [
            FstabEntry(
                fs_spec="PARTUUID={}".format(entry["part_uuid"]),
                fs_file=entry["mount_path"] or "none",
                fs_vfstype=entry["fs_name"],
                fs_mntops=entry["mount_opts"],
                fs_freq=0,
                fs_passno=1 if entry["mount_path"] == "/" else 2,
            )
            for entry in submission
            if entry["fs_name"] is not None and entry["mount_opts"] is not None
        ]

        return sorted(fstab, key=operator.itemgetter("fs_file"))

    def run(self, tmp: None = None, task_vars: TaskVars = None) -> RawResult:
        #
        # Validate basic syntax errors.
        #
        _, raw_args = self.validate_argument_spec(ARGS_SPEC)
        raw_vars = validate_spec(VARS_SPEC, self._templar.template(self._task.vars))

        #
        # Build general instances, preferably in the order of runtime requirements.
        #  (i.e. put the DeviceBuilder at the end as it calls ioctl).
        #
        modexec = ModuleExecutor(self, task_vars)
        layout = self._build_layout_frontage(modexec, raw_args, raw_vars)
        device = self._build_device_frontage(modexec, raw_args)

        #
        # Perform stages, one by one.
        #
        arrangement = ArrangementStage(self._display, modexec, device, layout)
        arrangement.run()

        #
        # From now, disk layout is assumed to be immutable.
        #  Further changes (such as creating a new filesystem) will not affect the disk layout.
        #
        submission = self._build_submission(modexec, device, layout)
        partitions = tuple(map(operator.itemgetter("part_path"), submission))
        if len(submission) != len(layout.frontages):
            raise AnsibleActionFail("Something went wrong. New layout changes were not reflected from the disk")

        formatter = FormatStage(modexec, device, layout)
        formatter.run(partitions)

        mounter = MountStage(modexec, device, layout)
        mounter.run(partitions)

        return RawResult(changed=not self._task.check_mode, submission=submission, fstab=self._build_fstab(submission))
