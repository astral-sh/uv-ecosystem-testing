import argparse
import concurrent.futures
import csv
import json
import os
import platform
import shutil
import subprocess
import time
import tomllib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from threading import Thread

import tomli_w
from tqdm.auto import tqdm

from uv_ecosystem_testing import (
    cache_dir,
    top_15k_pypi,
    top_15k_pypi_latest_version,
    Mode,
    RunConfig,
    pyproject_tomls_dir,
)


@dataclass
class Summary:
    package: str
    exit_code: int
    max_rss: int
    time: float


def run_uv(
    package: str,
    specification: str,
    uv: Path,
    mode: Mode,
    python: str,
    cache: Path,
    offline: bool,
    output: Path,
    i_am_in_docker: bool = False,
) -> Summary:
    """Resolve in a uv subprocess.

    The logic captures the max RSS from the process and avoids deadlocks from full
    pipes.
    """
    package_dir = output.joinpath(package)
    package_dir.mkdir()
    command = prepare_uv_command(
        specification, uv, mode, cache, offline, package_dir, python, i_am_in_docker
    )

    start = time.time()

    env = os.environ.copy()
    if "VIRTUAL_ENV" in env:
        del env["VIRTUAL_ENV"]

    process = subprocess.Popen(
        command,
        cwd=package_dir,
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    stdout, stderr = communicate(
        process, specification if mode == Mode.COMPILE else None
    )

    # At this point the process should be finished, stdout and stderr being closed usually means that.
    # The process is a zombie, so has called `exit()`, but we haven't reaped it with `wait`/`wait4` yet.

    # rusage is only available on unix
    if os.name == "posix":
        # Reap the process to get resource usage information.
        _pid, exit_code, rusage = os.wait4(process.pid, 0)
    else:
        exit_code = process.wait()
        rusage = None

    if mode == Mode.SYNC:
        venv = package_dir.joinpath(".venv")
        if venv.exists():
            shutil.rmtree(venv)

    max_rss = rusage.ru_maxrss if rusage else 0

    package_dir.joinpath("stdout.txt").write_text(stdout)
    package_dir.joinpath("stderr.txt").write_text(stderr)
    summary = Summary(
        package=package, exit_code=exit_code, max_rss=max_rss, time=time.time() - start
    )
    package_dir.joinpath("summary.json").write_text(json.dumps(summary.__dict__))
    return summary


def prepare_uv_command(
    specification: str,
    uv: Path,
    mode: Mode,
    cache: Path,
    offline: bool,
    package_dir: Path,
    python: str,
    i_am_in_docker: bool = False,
) -> list[Path | str]:
    shared_args = ["--cache-dir", cache, "--color", "never", "--no-python-downloads"]
    if not i_am_in_docker:
        shared_args.append("--no-build")
    if offline:
        shared_args.append("--offline")
    if mode == Mode.PYPROJECT_TOML:
        package_dir.joinpath("pyproject.toml").write_text(specification)
        command = [uv, "lock", *shared_args]
    elif mode == Mode.SYNC:
        package_dir.joinpath("pyproject.toml").write_text(specification)
        command = [uv, "sync", *shared_args, "--preview"]
        if not i_am_in_docker:
            command.append("--no-install-project")
    elif mode == Mode.LOCK:
        package_dir.joinpath("pyproject.toml").write_text(
            f"""
            [project]
            name = "testing"
            version = "0.1.0"
            requires-python = ">={python}"
            dependencies = ["{specification}"]
            """
        )
        command = [uv, "lock", *shared_args]
    elif mode == Mode.COMPILE:
        command = [
            uv,
            "pip",
            "compile",
            "-",
            "-p",
            python,
            # The results are more reproducible if they are platform independent
            "--universal",
            "--no-header",
            "--no-annotate",
            *shared_args,
        ]
    else:
        raise ValueError(f"Unknown mode: {mode}")
    return command


def communicate(process: subprocess.Popen, stdin: str | None) -> tuple[str, str]:
    """Like `Popen.communicate`, but without the `os.wait` call.

    Start threads to drain the pipes to avoid blocking on full pipes, but don't use
    libc's `wait` so we can use `os.wait4` later.
    """
    # If the process already exited, we get a `BrokenPipeError`.
    try:
        if stdin:
            process.stdin.write(stdin)
        process.stdin.close()
    except BrokenPipeError:
        pass

    # Mutable objects to communicate across threads
    stdout = []
    stderr = []

    def read_stdout():
        stdout.append(process.stdout.read())
        process.stdout.close()

    def read_stderr():
        stderr.append(process.stderr.read())
        process.stderr.close()

    stdout_thread = Thread(target=read_stdout, daemon=True)
    stderr_thread = Thread(target=read_stderr, daemon=True)
    stdout_thread.start()
    stderr_thread.start()
    stdout_thread.join()
    stderr_thread.join()

    return next(iter(stdout), ""), next(iter(stderr), "")


def resolve_all(
    input: Path,
    output: Path,
    mode: Mode,
    uv: Path,
    cache_dir: Path = cache_dir,
    python: str = "3.13",
    offline: bool = False,
    latest: bool = False,
    limit: int | None = None,
    stats: bool = False,
    i_am_in_docker: bool = False,
) -> None:
    if mode in [Mode.PYPROJECT_TOML, Mode.SYNC]:
        project_tomls = sorted((file.stem, file) for file in input.iterdir())
        jobs = {}
        no_project = 0
        dynamic_dependencies = 0
        for package, file in project_tomls:
            if limit and len(jobs) >= limit:
                break
            if file.suffix != ".toml":
                continue
            project_toml = file.read_text()
            data = tomllib.loads(project_toml)
            project = data.get("project")
            if not project:
                no_project += 1
                continue
            if dynamic := project.get("dynamic"):
                if "dependencies" in dynamic and not i_am_in_docker:
                    dynamic_dependencies += 1
                    continue
                if "version" in dynamic:
                    dynamic.remove("version")
                # Usually there are no cycles back to the current project, so any version works
                project["version"] = "1.0.0"

            jobs[package] = tomli_w.dumps(data)

        print(f"`pyproject.toml`s without `[project]`: {no_project}")
        if not i_am_in_docker:
            print(
                f"`pyproject.toml`s with `dynamic = ['dependencies']`: {dynamic_dependencies}"
            )
        if latest:
            raise ValueError("Latest versions are not supported in pyproject-toml mode")
    else:
        with input.open() as f:
            project_names = sorted(row["project"] for row in csv.DictReader(f))

        if latest:
            with top_15k_pypi_latest_version.open() as f:
                latest_versions = {
                    row["package_name"]: row["latest_version"]
                    for row in csv.DictReader(f)
                }
        else:
            latest_versions = None

        jobs = {}
        for package in project_names[:limit]:
            if latest_versions:
                if version := latest_versions.get(package):
                    jobs[package] = f"{package}=={version}"
                else:
                    tqdm.write(f"Missing version: {package}")
                    continue
            else:
                jobs[package] = package

    excluded_packages = [
        # 5000 releases, no solution
        "nucliadb",
        # These packages have many non-small versions
        "tf-models-nightly",
        "mtmtrain",
        "llm-dialog-manager",
        "python-must",
        # Slow and have no solution
        "edx-enterprise",
        "kcli",
        "emmet-api",
    ]
    for package in excluded_packages:
        jobs.pop(package, None)

    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    output.joinpath(".gitignore").write_text("*\n")
    RunConfig(
        mode=mode, python=python, latest=latest, i_am_in_docker=i_am_in_docker
    ).write(output)

    success = 0
    all_results = []  # Track all results for analysis
    max_package_len = max(len(package) for package in jobs)

    with ThreadPoolExecutor(max_workers=(os.cpu_count() or 1) * 2) as executor:
        tasks = []
        packages_pending = []
        for package, specification in jobs.items():
            packages_pending.append(package)

            tasks.append(
                executor.submit(
                    run_uv,
                    package,
                    specification,
                    uv,
                    mode,
                    python,
                    cache_dir,
                    offline,
                    output,
                    i_am_in_docker=i_am_in_docker,
                )
            )
        total = len(packages_pending)

        with tqdm(total=total) as progress_bar:
            for result in concurrent.futures.as_completed(tasks):
                summary = result.result()

                all_results.append(summary)
                progress_bar.update(1)
                packages_pending.remove(summary.package)
                if packages_pending:
                    progress_bar.set_postfix_str(
                        f"{packages_pending[0]:>{max_package_len}}"
                    )
                if summary.exit_code == 0:
                    success += 1

    print(f"Success: {success}/{total} ({success / total:.0%})")

    successes = [summary for summary in all_results if summary.exit_code == 0]

    if stats:
        print("\n# top 5 slowest resolutions for successes")
        slowest = sorted(successes, key=lambda x: x.time, reverse=True)[:5]
        for summary in slowest:
            print(
                f"{summary.package}: {summary.time:.2f}s (exit code: {summary.exit_code})"
            )

        if os.name == "posix":
            print("\n# top 5 max RSS for successes")
            largest_rss = sorted(successes, key=lambda x: x.max_rss, reverse=True)[:5]
            for summary in largest_rss:
                # On linux, max RSS is in KB, on macOS, it is in bytes
                if platform.system() == "Linux":
                    max_rss = summary.max_rss / 1024
                elif platform.system() == "Darwin":
                    max_rss = summary.max_rss / 1024 / 1024
                else:
                    raise NotImplementedError(f"Unknown platform: {platform.system()}")
                print(
                    f"{summary.package}: {max_rss:.1f} MB (exit code: {summary.exit_code})"
                )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=None)
    parser.add_argument(
        "--mode",
        choices=[mode.value for mode in Mode],
        default=Mode.COMPILE.value,
        help="`compile`: `uv pip compile`\n"
        + "`lock`: `uv lock` from a single requirement\n"
        + "`pyproject-toml`: `uv lock` from a directory of `pyproject.toml` files\n"
        + "`sync`: `uv sync` from a directory of `pyproject.toml` files",
    )
    parser.add_argument("--python", "-p", type=str, default="3.13")
    parser.add_argument("--output", type=Path, default="output")
    parser.add_argument("--uv", type=Path, default=Path("uv"))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--cache", type=Path, default=cache_dir)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--latest", action="store_true")
    parser.add_argument("--stats", action="store_true")
    parser.add_argument(
        "--i-am-in-docker",
        action="store_true",
        help="Execute arbitrary code while resolving. Use only in isolated environments such as docker.",
    )
    args = parser.parse_args()

    if not args.input:
        if Mode(args.mode) in [Mode.PYPROJECT_TOML, Mode.SYNC]:
            input_path = pyproject_tomls_dir
        else:
            input_path = top_15k_pypi
    else:
        input_path = args.input

    resolve_all(
        input_path,
        args.output,
        Mode(args.mode),
        args.uv,
        args.cache,
        args.python,
        args.offline,
        args.latest,
        args.limit,
        args.stats,
        args.i_am_in_docker,
    )


if __name__ == "__main__":
    main()
