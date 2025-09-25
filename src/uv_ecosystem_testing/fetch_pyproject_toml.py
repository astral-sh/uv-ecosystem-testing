import argparse
import asyncio
import csv
import shutil
from dataclasses import dataclass
from pathlib import Path

import httpx
from httpx import AsyncClient
from tqdm.auto import tqdm

from uv_ecosystem_testing import pyproject_tomls_dir


@dataclass
class Repository:
    org: str
    repo: str
    ref: str


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        action="append",
        type=Path,
        help="csv file(s) with a `repo_name` culumn and optionally a `ref` column",
    )
    parser.add_argument("--output", type=Path, default=pyproject_tomls_dir)
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args()

    asyncio.run(fetch_all_pyproject_toml(args.input, args.output, args.keep))


async def fetch_all_pyproject_toml(
    repositories_files: list[Path], output: Path, keep: bool = False
):
    repositories = []
    seen = set()
    for repositories_file in repositories_files:
        with repositories_file.open() as f:
            # Avoid duplicates
            for row in csv.DictReader(f):
                if row["repo_name"] in seen:
                    continue
                seen.add(row["repo_name"])
                repositories.append(
                    Repository(
                        org=row["repo_name"].split("/")[0],
                        repo=row["repo_name"].split("/")[1],
                        # Use master so we try to master and main
                        ref=row.get("ref", "refs/heads/master"),
                    )
                )

    if not keep and output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    output.joinpath(".gitignore").write_text("*\n")

    semaphore = asyncio.Semaphore(50)

    async def fetch_with_semaphore(
        client: AsyncClient, repository: Repository, output_dir: Path
    ):
        async with semaphore:
            return await fetch_one(client, repository, output_dir)

    async with httpx.AsyncClient() as client:
        with tqdm(total=len(repositories)) as pbar:
            tasks = [
                fetch_with_semaphore(client, repository, output)
                for repository in repositories
            ]
            results = []
            for future in asyncio.as_completed(tasks):
                results.append(await future)
                pbar.update(1)

    success = sum(1 for result in results if result is True)
    print(f"Successes: {success}/{len(repositories)}")


async def fetch_one(client: AsyncClient, repository: Repository, output_dir: Path):
    url = f"https://raw.githubusercontent.com/{repository.org}/{repository.repo}/{repository.ref}/pyproject.toml"
    try:
        response = await client.get(url)
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        # The bigquery data is sometimes missing the master -> main transition
        url = f"https://raw.githubusercontent.com/{repository.org}/{repository.repo}/refs/heads/main/pyproject.toml"
        try:
            response = await client.get(url)
            response.raise_for_status()
        except httpx.HTTPError:
            # Ignore the error from the main fallback if it didn't work
            if e.response.status_code == 404:
                tqdm.write(
                    f"Not found: https://github.com/{repository.org}/{repository.repo}"
                )
            else:
                tqdm.write(
                    f"Error for https://github.com/{repository.org}/{repository.repo}: {e}"
                )
            return None
    except httpx.HTTPError as e:
        tqdm.write(
            f"Error for https://github.com/{repository.org}/{repository.repo}: {e}"
        )
        return None
    output_dir.joinpath(f"{repository.repo}.toml").write_text(response.text)
    return True


if __name__ == "__main__":
    main()
