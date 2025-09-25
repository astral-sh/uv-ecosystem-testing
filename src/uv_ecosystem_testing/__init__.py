import json
import os
from dataclasses import dataclass
from enum import Enum
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


class Mode(Enum):
    COMPILE = "compile"
    LOCK = "lock"
    PYPROJECT_TOML = "pyproject-toml"


@dataclass
class RunConfig:
    """The parameters of a run, stored in a JSON file in the output directory."""

    mode: Mode
    python: str
    latest: bool
    i_am_in_docker: bool

    def write(self, output_dir: Path):
        data = self.__dict__.copy()
        data["mode"] = self.mode.value if isinstance(self.mode, Mode) else self.mode
        output_dir.joinpath("parameters.json").write_text(json.dumps(data))

    @staticmethod
    def read(output_dir: Path) -> "RunConfig":
        parameters = json.loads(output_dir.joinpath("parameters.json").read_text())
        parameters["mode"] = Mode(parameters["mode"])
        return RunConfig(**parameters)
