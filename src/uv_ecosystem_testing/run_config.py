import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class RunConfig:
    """The parameters of a run, stored in a JSON file in the output directory."""

    mode: str
    python: str
    latest: bool
    i_am_in_docker: bool

    def write(self, output_dir: Path):
        output_dir.joinpath("parameters.json").write_text(json.dumps(self.__dict__))

    @staticmethod
    def read(output_dir: Path) -> "RunConfig":
        parameters = json.loads(output_dir.joinpath("parameters.json").read_text())
        return RunConfig(**parameters)
