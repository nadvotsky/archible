#!/usr/bin/env python3

import typing

import argparse
import pathlib
import re
import itertools
import tempfile
import subprocess
import json
import sys


SOURCES = ["src", "test"]
SOURCES_ALLOW_EXT = [".h", ".hh", ".hpp", ".hxx", ".c", ".cc", ".cpp", ".cxx"]

BUILD = "build"
BUILD_IGNORE_PATTERN = "_deps"

CLANG_TIDY_CONFIG = "config/lint/clang-tidy.yml"
CLANG_FORMAT_CONFIG = "config/format/clang-format.yml"


def run_external_command(cmdline: typing.Sequence[str]) -> None:
    print()
    print(f"> {' '.join(cmdline)}")
    print()

    subprocess.run(
        cmdline,
        stdout=sys.stdout,
        stderr=sys.stderr,
        check=True,
    )


def run_clang_tidy(
    project: pathlib.Path,
    sources: typing.Iterable[str],
    bazel_config: str | None = None,
) -> None:
    if bazel_config is not None:
        run_external_command(
            [
                "bazel-compile-commands",
                "--arguments",
                "--bazel-command", "bazelisk",
                "--config", bazel_config,
                "--output", str(project / BUILD / "compile_commands.json"),
            ]
        )

    clang_tidy_common_args = [
        "clang-tidy",
        "--quiet",
        "--use-color", f"--config-file={str(project / CLANG_TIDY_CONFIG)}",
        "-p", str(project / BUILD),
    ]

    compile_commands = json.loads(
        project.joinpath(BUILD, "compile_commands.json").read_text()
    )
    filtered_commands = [
        command
        for command in compile_commands
        if BUILD_IGNORE_PATTERN not in pathlib.Path(command["file"]).parts
    ]
    if len(compile_commands) == len(filtered_commands):
        return run_external_command([*clang_tidy_common_args, *sources])

    with tempfile.TemporaryDirectory() as tempdir:
        overlay_dir = pathlib.Path(tempdir)

        overlayed_commands = overlay_dir / "compile_commands.json"
        overlayed_commands.write_text(json.dumps(filtered_commands))

        overlay = dict(
            version=0,
            roots=[
                {
                    "name": "compile_commands.json",
                    "type": "file",
                    "external-contents": str(overlayed_commands),
                }
            ],
        )
        overlay_file = overlay_dir / "overlay.yml"
        overlay_file.write_text(json.dumps(overlay))

        run_external_command(
            [*clang_tidy_common_args, f"--vfsoverlay={str(overlay_file)}", *sources]
        )


def run_clang_format(project: pathlib.Path, sources: typing.Iterable[str]) -> None:
    run_external_command(
        [
            "clang-format",
            f"--style=file:{str(project / CLANG_FORMAT_CONFIG)}",
            "-i",
            *sources,
        ]
    )


def main():
    project = pathlib.Path()

    parser = argparse.ArgumentParser(description="Extra C++ developement tasks")
    subparsers = parser.add_subparsers(dest="subcommand")

    clang_tidy = subparsers.add_parser("lint", help="Run clang-tidy linter")
    if project.joinpath("MODULE.bazel").is_file():
        bazel_configs = set(
            re.findall(
                r"^build:([\w\d_-]+)", project.joinpath(".bazelrc").read_text(), re.M
            )
        )
        clang_tidy = clang_tidy.add_argument(
            "config", choices=bazel_configs, help="Bazel configuration to run."
        )

    _ = subparsers.add_parser(
        "fmt", aliases=["format"], help="Run clang-format formatter"
    )

    args = parser.parse_args()
    sources = tuple(
        str(source)
        for source in itertools.chain.from_iterable(
            (project.glob(f"{source}/**/*.*") for source in SOURCES)
        )
        if source.suffix in SOURCES_ALLOW_EXT
    )
    if not len(sources):
        raise Exception("No sources found.")

    match args.subcommand:
        case "lint":
            run_clang_tidy(project, sources, vars(args).get("config"))
        case "fmt" | "format":
            run_clang_format(project, sources)
        case _:
            parser.print_help()


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, subprocess.CalledProcessError):
        pass
