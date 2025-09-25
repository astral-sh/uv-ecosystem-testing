import argparse
import difflib
import json
import re
import sys
from pathlib import Path
from typing import TextIO

from uv_ecosystem_testing.run_config import RunConfig


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("base", type=Path)
    parser.add_argument("branch", type=Path)
    parser.add_argument("--markdown", action="store_true")
    args = parser.parse_args()
    create_report(args.base, args.branch, args.markdown)


def create_report(
    base: Path, branch: Path, markdown: bool = False, writer: TextIO = sys.stdout
) -> None:
    # Supress noise from fluctuations in execution time
    redact_time = re.compile(r"(0\.)?(\d+)ms|(\d+).(\d+)s")

    parameters = RunConfig.read(base)
    parameters_branch = RunConfig.read(branch)
    if parameters != parameters_branch:
        raise RuntimeError(
            f"Parameters differ between runs:\n   base: {parameters}\n   branch: {parameters_branch}"
        )

    total = 0
    successful = 0
    differences = []
    fixed = []
    files = sorted(dir for dir in base.iterdir() if dir.is_dir())
    for package_base in files:
        package = package_base.name
        package_branch = branch.joinpath(package)
        if not package_branch.is_dir():
            writer.write(f"Package {package} not found in branch\n")
            continue

        total += 1

        summary_base = package_base.joinpath("summary.json").read_text()
        summary_branch = package_branch.joinpath("summary.json").read_text()
        if json.loads(summary_base)["exit_code"] == 0:
            successful += 1
        else:
            if json.loads(summary_branch)["exit_code"] == 0:
                fixed.append(package)
            # Don't show differences in the error messages,
            # also `uv.lock` doesn't exist for failed resolutions
            continue

        if parameters.mode == "compile":
            resolution = package_base.joinpath("stdout.txt").read_text()
        else:
            resolution = package_base.joinpath("uv.lock").read_text()
            if package_base.joinpath("stdout.txt").read_text().strip():
                raise RuntimeError(f"Stdout not empty (base): {package}")
        stderr = package_base.joinpath("stderr.txt").read_text()
        stderr = redact_time.sub(r"[TIME]", stderr)

        if parameters.mode == "compile":
            resolution_branch = package_branch.joinpath("stdout.txt").read_text()
        else:
            resolution_branch = package_branch.joinpath("uv.lock").read_text()
            if package_branch.joinpath("stdout.txt").read_text().strip():
                raise RuntimeError(f"Stdout not empty (branch): {package}")
        stderr_branch = package_branch.joinpath("stderr.txt").read_text()
        stderr_branch = redact_time.sub(r"[TIME]", stderr_branch)

        if resolution != resolution_branch or stderr != stderr_branch:
            differences.append(
                (package, resolution, resolution_branch, stderr, stderr_branch)
            )

    if markdown:
        writer.write(
            f"**{parameters.mode.replace('pyproject-toml', 'pyproject.toml')}**\n"
        )
        if parameters.mode == "pyproject-toml":
            writer.write(
                " * Dataset: A set of top level `pyproject.toml` from GitHub projects popular in 2025. "
                + "Only `pyproject.toml` files with a `[project]` section and static dependencies are included.\n"
            )
        else:
            writer.write(
                " * Dataset: The top 15k PyPI packages. A handful of pathological cases were filtered out.\n"
            )
        writer.write(
            " * Command: "
            + f"`{'uv pip compile' if parameters.mode == 'compile' else 'uv lock'}` "
            + ("with `--no-build` " if not parameters.i_am_in_docker else "")
            + (
                "with packages pinned to the latest version"
                if parameters.latest
                else ""
            )
            + f"on Python {parameters.python}."
            + "\n"
        )
        writer.write(
            f" * Successfully resolved packages: {successful}/{total} ({successful / total:.0%}). "
            + "Only success resolutions can be compared.\n"
        )
        writer.write("\n")
        if len(differences) == 0:
            writer.write(f"All resolutions are identical ({successful} total).\n\n")
        else:
            writer.write(f"Different resolutions: {len(differences)}/{successful}\n")

        if fixed:
            writer.write("**Packages fixed in branch**\n")
            for fixed_package in fixed:
                writer.write(f"* {fixed_package}\n")
            writer.write("\n")

        for (
            package,
            resolution,
            resolution_branch,
            stderr,
            stderr_branch,
        ) in differences:
            writer.write(f"\n<details>\n<summary>{package}</summary>\n\n")
            if resolution != resolution_branch:
                writer.write("```diff\n")
                writer.writelines(
                    difflib.unified_diff(
                        resolution.splitlines(keepends=True),
                        resolution_branch.splitlines(keepends=True),
                        fromfile="base",
                        tofile="branch",
                        n=0,
                    )
                )
                writer.write("\n```\n")
            if stderr != stderr_branch:
                writer.write("```diff\n")
                writer.writelines(
                    difflib.unified_diff(
                        stderr.splitlines(keepends=True),
                        stderr_branch.splitlines(keepends=True),
                        fromfile="base",
                        tofile="branch",
                        n=0,
                    )
                )
                writer.write("```\n")
            writer.write("</details>\n\n")
    else:
        for (
            package,
            resolution,
            resolution_branch,
            stderr,
            stderr_branch,
        ) in differences:
            writer.write("--------------------------------\n")
            writer.write(f"Package {package}\n")
            if resolution != resolution_branch:
                writer.writelines(
                    difflib.unified_diff(
                        resolution.splitlines(keepends=True),
                        resolution_branch.splitlines(keepends=True),
                        fromfile="base",
                        tofile="branch",
                    )
                )
            if stderr != stderr_branch:
                writer.writelines(
                    difflib.unified_diff(
                        stderr.splitlines(keepends=True),
                        stderr_branch.splitlines(keepends=True),
                        fromfile="base",
                        tofile="branch",
                    )
                )

        if fixed:
            writer.write("--------------------------------\n")
            writer.write("Packages fixed in branch\n")
            for fixed_package in fixed:
                writer.write(f"* {fixed_package}\n")
            writer.write("\n")

        writer.write(
            f"Successfully resolved packages: {successful}/{total} ({successful / total:.0%})\n"
        )
        if len(differences) == 0:
            writer.write(f"All resolutions are identical ({successful} total).\n")
        else:
            writer.write(f"Different resolutions: {len(differences)}/{successful}\n")


if __name__ == "__main__":
    main()
