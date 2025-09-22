import argparse
import asyncio
import csv
import shutil
from dataclasses import dataclass
from pathlib import Path

import httpx
from httpx import AsyncClient
from tqdm.auto import tqdm

from uv_ecosystem_testing import data_dir


@dataclass
class Repository:
    org: str
    repo: str
    ref: str


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        type=Path,
        default=data_dir.joinpath("top5k_pyproject_toml_2025_gh_stars.csv"),
    )
    parser.add_argument(
        "--output", type=Path, default=data_dir.joinpath("pyproject_toml")
    )
    args = parser.parse_args()

    asyncio.run(fetch_all_pyproject_toml(args.input, args.output))


async def fetch_all_pyproject_toml(repositories: Path, output: Path):
    with repositories.open() as f:
        repositories = []
        # Avoid duplicates
        seen = set()
        for row in csv.DictReader(f):
            if row["repo_name"] in seen:
                continue
            seen.add(row["repo_name"])
            repositories.append(
                Repository(
                    org=row["repo_name"].split("/")[0],
                    repo=row["repo_name"].split("/")[1],
                    ref=row["ref"],
                )
            )

    if output.exists():
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
    except httpx.HTTPError as e:
        # The bigquery data is sometimes missing the master -> main transition
        url = f"https://raw.githubusercontent.com/{repository.org}/{repository.repo}/refs/heads/main/pyproject.toml"
        try:
            response = await client.get(url)
            response.raise_for_status()
        except httpx.HTTPError:
            # Ignore the error from the main fallback if it didn't work
            if hasattr(e, "response") and e.response.status_code == 404:
                tqdm.write(
                    f"Not found: https://github.com/{repository.org}/{repository.repo}"
                )
            else:
                tqdm.write(
                    f"Error for https://github.com/{repository.org}/{repository.repo}: {e}"
                )
            return None

    output_dir.joinpath(f"{repository.repo}.toml").write_text(response.text)
    return True


if __name__ == "__main__":
    main()
