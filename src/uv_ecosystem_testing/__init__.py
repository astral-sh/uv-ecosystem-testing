from pathlib import Path

root_dir = Path(__file__).parent.parent.parent
data_dir = root_dir.joinpath("data")
cache_dir = root_dir.joinpath("cache")
