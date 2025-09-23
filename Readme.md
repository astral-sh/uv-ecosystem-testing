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

## Modes and data

There are three factors that have a major impact on the resolution and its
output:

- platform-specific resolution creates a flat list, while universal resolution
  uses markers and capture a list of platforms. `uv pip` can use both
  platform-specific and universal resolution, while `uv lock` always uses
  universal resolution.
- The `uv pip` interface outputs the `requirements.txt` format, while `uv lock`
  outputs `uv.lock.
- A single requirement vs. a workspace with extras, groups and workspace
  members.

To cover this area, there are three supported modes:

- compile: Run `uv pip compile` with a single package
- lock: Run `uv lock` on a `pyproject.toml` with a single package in
  `project.dependencies`
- pyproject-toml: Run `uv lock` on prepared `pyproject.toml` files.

For compile and lock, the default dataset is the top 15k PyPI packages from
https://hugovk.github.io/top-pypi-packages/, with one capturing the
`requirements.txt` output and the other capturing the `uv.lock` output.

For pyproject-toml, `pyproject.toml` files from popular GitHub projects are
used. Data from the [GH Archive](https://www.gharchive.org/) was queried with
[`top5k-pyproject-toml-2025-gh-stars.sql`](data/top5k-pyproject-toml-2025-gh-stars.sql).
This dataset captures more uv and resolver functionality but is also much
smaller. The corresponding `pyproject.toml` files can be downloaded with:

```shell
uv run python -m uv_ecosystem_testing.fetch_pyproject_toml
```

While it's possible to download and generate all data files on demand, it
generates a lot of API requests each time and adds more changes between runs. On
the other hands, the `pyproject.toml` files are too many to include in Git. As a
compromise, the top 15k PyPI packages and latest version list are included in
the repository, while the `pyproject.toml` files are cache locally.

## Safety and docker

All operations run with `--no-build` to allow resolving arbitrary requirements
without further isolation.

It's possible to run the resolution in a docker container and allow building
source distributions during resolution.

```
docker build . -t uv-ecosystem-testing
docker run -it --rm -v .:/io:ro -v ./docker:/work -e UV_ECOSYSTEM_TESTING_ROOT=/io uv-ecosystem-testing --base /work/base --branch /work/branch --report /work/Report.md --cache /work/cache --i-am-in-docker /io/uv-main /io/uv-prio-changes
```
