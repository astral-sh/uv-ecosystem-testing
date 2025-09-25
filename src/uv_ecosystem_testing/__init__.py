import os
from pathlib import Path

# TODO(konsti): Provider a way to set the root in the CLI and derive all paths from that.
root_dir = Path(
    os.environ.get("UV_ECOSYSTEM_TESTING_ROOT") or Path(__file__).parent.parent.parent
)

data_dir = root_dir.joinpath("data")
top5k_pyproject_toml_2025_gh_stars = data_dir.joinpath(
    "top5k-pyproject-toml-2025-gh-stars.csv"
)
mypy_primer = data_dir.joinpath("mypy-primer.csv")
top_15k_pypi = data_dir.joinpath("top-15k-pypi.csv")
top_15k_pypi_latest_version = data_dir.joinpath("top-15k-pypi-latest-version.csv")

pyproject_tomls_dir = root_dir.joinpath("pyproject_tomls")

cache_dir = root_dir.joinpath("cache")
