import argparse
import asyncio
from pathlib import Path

from uv_ecosystem_testing import cache_dir, data_dir, root_dir
from uv_ecosystem_testing.report import create_report
from uv_ecosystem_testing.fetch_pyproject_toml import fetch_all_pyproject_toml
from uv_ecosystem_testing.resolve import resolve_all


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("uv_base", type=Path)
    parser.add_argument("uv_branch", type=Path)
    parser.add_argument("--base", type=Path, default=root_dir.joinpath("base"))
    parser.add_argument("--branch", type=Path, default=root_dir.joinpath("branch"))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--report", type=Path, default=None)
    parser.add_argument("--latest", action="store_true")
    parser.add_argument("--only-report", action="store_true")
    parser.add_argument("--python", type=str, default="3.13")
    args = parser.parse_args()

    asyncio.run(
        run(
            args.uv_base,
            args.uv_branch,
            args.base,
            args.branch,
            limit=args.limit,
            report=args.report,
            latest=args.latest,
            python=args.python,
            only_report=args.only_report,
        )
    )


async def run(
    uv_base: Path,
    uv_branch: Path,
    base: Path,
    branch: Path,
    limit: int | None = None,
    report: Path | None = None,
    latest: bool = False,
    python: str = "3.13",
    only_report: bool = False
):
    base.mkdir(exist_ok=True, parents=True)
    branch.mkdir(exist_ok=True, parents=True)

    top_15k_pypi = data_dir.joinpath("top-15k-pypi.csv")
    top5k_pyproject_toml_2025_gh_stars = data_dir.joinpath(
        "top5k_pyproject_toml_2025_gh_stars.csv"
    )
    pyproject_tomls = data_dir.joinpath("pyproject_toml")

    if not pyproject_tomls.is_dir():
        await fetch_all_pyproject_toml(
            top5k_pyproject_toml_2025_gh_stars, pyproject_tomls
        )

    if not only_report:
        resolve_all(
            top_15k_pypi,
            base.joinpath("compile"),
            "compile",
            uv_base,
            cache_dir=cache_dir,
            limit=limit,
            latest=latest,
            python=python,
        )
        resolve_all(
            top_15k_pypi,
            branch.joinpath("compile"),
            "compile",
            uv_branch,
            cache_dir=cache_dir,
            limit=limit,
            latest=latest,
            python=python,
        )
        resolve_all(
            top_15k_pypi,
            base.joinpath("lock"),
            "lock",
            uv_base,
            cache_dir,
            limit=limit,
            latest=latest,
            python=python,
        )
        resolve_all(
            top_15k_pypi,
            branch.joinpath("lock"),
            "lock",
            uv_branch,
            cache_dir,
            limit=limit,
            latest=latest,
            python=python,
        )
        resolve_all(
            pyproject_tomls,
            base.joinpath("pyproject-toml"),
            "pyproject-toml",
            uv_base,
            cache_dir=cache_dir,
            limit=limit,
            latest=latest,
            python=python,
        )
        resolve_all(
            pyproject_tomls,
            branch.joinpath("pyproject-toml"),
            "pyproject-toml",
            uv_branch,
            cache_dir=cache_dir,
            limit=limit,
            latest=latest,
            python=python,
        )

    create_report(
        base.joinpath("compile"),
        branch.joinpath("compile"),
        "compile",
        False,
    )
    create_report(
        base.joinpath("lock"),
        branch.joinpath("lock"),
        "lock",
        False,
    )
    create_report(
        base.joinpath("pyproject-toml"),
        branch.joinpath("pyproject-toml"),
        "pyproject-toml",
        False,
    )

    if report:
        with report.open("w") as writer:
            writer.write("## Ecosystem testing report\n")
            create_report(
                base.joinpath("compile"),
                branch.joinpath("compile"),
                "compile",
                True,
                writer,
            )
            create_report(
                base.joinpath("lock"),
                branch.joinpath("lock"),
                "lock",
                True,
                writer,
            )
            create_report(
                base.joinpath("pyproject-toml"),
                branch.joinpath("pyproject-toml"),
                "pyproject-toml",
                True,
                writer,
            )


if __name__ == "__main__":
    main()
