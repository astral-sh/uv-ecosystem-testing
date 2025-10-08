# Ecosystem scale testing for uv

Compare the resolution for a large number of packages between two uv binaries.
This helps with assessing changes to the resolver, both for `uv pip compile` and
for `uv lock`. The tool runs different resolutions with both binaries and
compiles a comparison of the outputs.

## Quickstart

Prepare two uv binaries, ideally release or profiling builds. Run:

```shell
uv run python -m uv_ecosystem_testing.run /path/to/uv1 /path/to/uv2 --report Report.md
```

In a hurry? Try `--limit 100` for fast results.

To test in a specific mode with specific options, for example `uv sync`:

```
uv run python -m uv_ecosystem_testing.resolve --mode sync --uv ./uv-main --output base/sync
uv run python -m uv_ecosystem_testing.resolve --mode sync --uv ./uv-branch --output branch/sync
uv run python -m uv_ecosystem_testing.report base/sync branch/sync
```

## Data and modes

There are three factors that have a major impact on the resolution and its
output:

- platform-specific resolution creates a flat list, while universal resolution
  uses markers and capture a list of platforms. `uv pip` can use both
  platform-specific and universal resolution, while `uv lock` always uses
  universal resolution.
- The `uv pip` interface outputs the `requirements.txt` format, while `uv lock`
  outputs `uv.lock`.
- A single requirement vs. a workspace with extras, groups and workspace
  members.

To cover them, there are three supported modes:

- compile: Run `uv pip compile` with a single package.
- lock: Run `uv lock` on a `pyproject.toml` with a single package in
  `project.dependencies`.
- pyproject-toml: Run `uv lock` on prepared `pyproject.toml` files.

For compile and lock, the default dataset is the top 15k PyPI packages from
https://hugovk.github.io/top-pypi-packages/, with one capturing the
`requirements.txt` output and the other capturing the `uv.lock` output.

For pyproject-toml, `pyproject.toml` files are collected from popular GitHub
projects by querying [GH Archive](https://www.gharchive.org/) data with
[`top5k-pyproject-toml-2025-gh-stars.sql`](data/top5k-pyproject-toml-2025-gh-stars.sql)
and by using the
[mypy primer project](https://github.com/hauntsaninja/mypy_primer/blob/0d20fff78b67f11f4dcbeb3d9b1c645b7198db5e/mypy_primer/projects.py),
both published under the MIT license. This dataset captures more uv and resolver
functionality but is also much smaller. The corresponding `pyproject.toml` files
can be downloaded with:

```shell
uv run python -m uv_ecosystem_testing.fetch_pyproject_toml --input data/mypy-primer.csv --input data/top5k-pyproject-toml-2025-gh-stars.csv
```

While it's possible to download and generate all data files on demand, it
generates a lot of API requests each time and adds more changes between runs. On
the other hands, the `pyproject.toml` files are too many to include in Git. As a
compromise, the top 15k PyPI packages, mypy primer and latest version list are
included in the repository, while the `pyproject.toml` files are cache locally.

## Safety and docker

By default, resolutions run with `--no-build` to allow resolving arbitrary
requirements without
[running arbitrary build scripts locally](https://moyix.blogspot.com/2022/09/someones-been-messing-with-my-subnormals.html).

It's possible to run the resolution in a docker container and build source
distributions during resolution. This increases the dataset coverage. This run
should be isolated from the host system as those builds run arbitrary code,
which here includes mounting the project directory read-only (`.:/io:ro`).

```
docker build . -t uv-ecosystem-testing
docker run -it --rm -v .:/io:ro -v ./docker:/work -e UV_ECOSYSTEM_TESTING_ROOT=/io uv-ecosystem-testing -m uv_ecosystem_testing.run --base /work/base --branch /work/branch --report /work/Report.md --cache /work/cache --i-am-in-docker /io/uv-main /io/uv-prio-changes
```

Example usage with `uv sync`:

```
# Prime the build caches
docker run -it --rm -v .:/io:ro -v ./docker:/work -e UV_ECOSYSTEM_TESTING_ROOT=/io \
    uv-ecosystem-testing -m uv_ecosystem_testing.resolve \
    --cache /work/cache --mode sync --uv /io/uv-main --output /work/base/sync --i-am-in-docker
docker run -it --rm -v .:/io:ro -v ./docker:/work -e UV_ECOSYSTEM_TESTING_ROOT=/io \
    uv-ecosystem-testing -m uv_ecosystem_testing.resolve \
    --cache /work/cache --mode sync --uv /io/uv-branch --output /work/branch/sync --i-am-in-docker

docker run -it --rm -v .:/io:ro -v ./docker:/work -e UV_ECOSYSTEM_TESTING_ROOT=/io \
    uv-ecosystem-testing -m uv_ecosystem_testing.resolve \
    --cache /work/cache --mode sync --uv /io/uv-main --output /work/base/sync --i-am-in-docker --offline
docker run -it --rm -v .:/io:ro -v ./docker:/work -e UV_ECOSYSTEM_TESTING_ROOT=/io \
    uv-ecosystem-testing -m uv_ecosystem_testing.resolve \
    --cache /work/cache --mode sync --uv /io/uv-branch --output /work/branch/sync --i-am-in-docker --offline

docker run -it --rm -v .:/io:ro -v ./docker:/work -e UV_ECOSYSTEM_TESTING_ROOT=/io \
    uv-ecosystem-testing -m uv_ecosystem_testing.report \
    /work/base/sync /work/branch/sync
```
