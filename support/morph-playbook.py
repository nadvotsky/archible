#!/usr/bin/env python

#
# morph-playbook - wrapper over the playbook launch routine for multiple hosts.
#
# This scripts features:
#  1) dynamic patching of the playbook file for specific host.
#  2) set of features that dynamically modify variables and tags.
#
# This still requires to create a separate tuned inventory, but allows to omit repetitive boilerplate,
#  especially when working with multiple hosts within restricted environments such as ArchISO.
# Practically this means there is no need to clone the entire configuration (playbook.yml + ansible.cfg + custom script)
#  for tiny ad-hoc scenarios that only modify few variables and/or tags. Instead, this functionality is provided by
#  this script that allows to implement such behavior via the command-line interface.
#
# Examples:
#  - python support/morph-playbook.py -X no-wayland -X no-portal -H laptop_{1}
#     - run the playbook.yml,
#     - skipping wayland and portal orchestration,
#     - and patching 'hosts: example_*' to 'hosts: laptop_*'.
#
#  - python support/morph-playbook.py -H laptop_local extra ^extra-backup
#     - run the playbook.yml,
#     - enabling the 'extra' tag (the maintenance step),
#     - skipping the 'extra-backup' tag,
#     - on the 'laptop_local' host.
#

import typing
import collections

import dataclasses
import argparse
import difflib
import pathlib

import json
import re

import shutil
import shlex
import os


@dataclasses.dataclass(frozen=True, kw_only=True)
class Feature:
    variables: dict[str, str] = dataclasses.field(default_factory=dict)
    exclude_tags: collections.abc.Sequence[str] = dataclasses.field(default_factory=tuple)
    include_tags: collections.abc.Sequence[str] = dataclasses.field(default_factory=tuple)


FEATURES = {
    "no-apex-desktop-wayland": Feature(
        variables=dict(ic_wayland="false"),
        exclude_tags=["apex-desktop-wayland"],
    ),
    "no-apex-desktop-portal": Feature(
        exclude_tags=(
            "apex-desktop-portal",
            "apex-desktop-x11-portal",
            "apex-desktop-wayland-portal",
        ),
    ),
    "no-apex-apps-jetbrains": Feature(
        exclude_tags=["apex-apps-jetbrains"],
    ),
    "no-dev-containers": Feature(
        exclude_tags=["apex-dev-containers"],
    ),
}


def cli_parse() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="archible playbook crafter")
    parser.add_argument(
        "-X",
        "--feature",
        action="append",
        metavar="{" + ", ".join(tuple(FEATURES.keys())) + "}",
        help="dynamic presets that modify tags and variables. Supports partial matching",
    )
    parser.add_argument(
        "-H",
        "--host",
        metavar="host",
        help=(
            "a template that replaces the 'hosts' field in playbook. "
            "Placeholders are filled with split parts of the original value (e.g. my_{1} + example_apex = my_apex)"
        ),
        required=True,
    )
    parser.add_argument(
        "-V",
        "--var",
        action="append",
        metavar="key=val",
        help="Additional variables to inject",
    )
    parser.add_argument(
        "tag",
        nargs="*",
        help="additional tags to configure. Skipped if prefixed '^' and included otherwise",
    )

    return parser.parse_args()


def cli_process_features(requests: collections.abc.Sequence[str]) -> list[Feature]:
    features, available_features = [], tuple(FEATURES.keys())
    for request in requests:
        matches = difflib.get_close_matches(request, available_features, n=1, cutoff=0.4)
        if not matches:
            raise ValueError("Feature '{}' does not even closely match any of: {}".format(request, available_features))

        features.append(FEATURES[matches[0]])
        print(" +feat: {} ({})".format(request, matches[0], features[-1]))

    return features


def cli_process_variables(expressions: collections.abc.Sequence[str]) -> dict[str, str]:
    variables = {}
    for pair in expressions:
        key, *value = pair.split("=", maxsplit=1)
        if len(value) != 1:
            raise ValueError(f"Invalid key-value pair '{pair}'")

        variables[key] = value[0]
        print(" +vars: {} ({})".format(key, value[0]))

    return variables


def cli_process_tags(expressions: collections.abc.Sequence[str]) -> tuple[list[str], list[str]]:
    include_tags, exclude_tags = [], []
    for tag in expressions:
        match tuple(tag):
            case ("^", *rest):
                exclude_tags.append("".join(rest))
                print(" +tags: {} (skip)".format(exclude_tags[-1]))

            case _:
                include_tags.append(tag)
                print(" +tags: {} (include)".format(include_tags[-1]))

    return include_tags, exclude_tags


def cli_process() -> tuple[str, dict[str, str], list[str], list[str]]:
    namespace = cli_parse()
    print(namespace)

    variables = cli_process_variables(namespace.var or tuple())
    include_tags, exclude_tags = cli_process_tags(namespace.tag)

    for feature in cli_process_features(namespace.feature or tuple()):
        variables.update(feature.variables)
        include_tags.extend(feature.include_tags)
        exclude_tags.extend(feature.exclude_tags)

    return namespace.host, variables, include_tags, exclude_tags


def playbook_patch(host: str, playbook: pathlib.Path) -> str:
    split_regex = re.compile(r"-|_")

    def host_repl(match: re.Match) -> str:
        prelude, original = match.groups()
        replacement = host.format(*split_regex.split(original))

        print(" +host: {} ({})".format(replacement, original))

        return f"{prelude}{replacement}"

    return re.sub(
        pattern=r"(?P<prelude>^\s+hosts:\s*)(?P<stage>[\w-]+)$",
        repl=host_repl,
        string=playbook.read_text(),
        flags=re.MULTILINE,
    )


def playbook_process(playbook: pathlib.Path, host: str, cmdline: list[str]) -> typing.Never:
    memfd = pathlib.Path("/dev/fd/{}".format(os.memfd_create("playbook", flags=0)))
    memfd.write_bytes(playbook_patch(host, playbook).encode())

    binary, arguments = shutil.which("ansible-playbook"), [*cmdline, str(memfd)]

    print()
    print(" +exec: {} {}".format(binary, shlex.join(arguments)))
    print()

    os.execv(binary, [binary, *arguments])


if __name__ == "__main__":
    playbook = pathlib.Path("./playbook.yml")
    host, variables, include_tags, exclude_tags = cli_process()

    cmdline = []

    if include_tags:
        cmdline.append("--tags")
        cmdline.append(",".join(include_tags))

    if exclude_tags:
        cmdline.append("--skip-tags")
        cmdline.append(",".join(exclude_tags))

    if variables:
        cmdline.append("--extra-vars")
        cmdline.append(json.dumps(variables))

    playbook_process(playbook, host, cmdline)
