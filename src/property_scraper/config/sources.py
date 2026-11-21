import logging
import threading
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Optional

from property_scraper.domain import MarketType, PropertyType, SearchSpec, TransactionType

logger = logging.getLogger(__name__)

DEFAULT_SOURCES_FILE = Path(__file__).with_name("sources.toml")


@dataclass(frozen=True)
class SourceConfig:
	spec: SearchSpec
	enabled: bool = True


def load_sources(path: Optional[Path] = None) -> list[SourceConfig]:
	path = path or DEFAULT_SOURCES_FILE
	with path.open("rb") as file:
		data = tomllib.load(file)

	sources = []
	for index, entry in enumerate(data.get("sources") or [], start=1):
		try:
			spec = SearchSpec(
				portal=entry["portal"],
				transaction=TransactionType(entry["transaction"]),
				property_type=PropertyType(entry["property_type"]),
				market=MarketType(entry["market"]))
			enabled = entry.get("enabled", True)
			if not isinstance(enabled, bool):
				raise ValueError(f"enabled must be true or false, got {enabled!r}")
		except (KeyError, ValueError) as e:
			raise ValueError(f"Invalid source #{index} in {path}: {e}") from e
		sources.append(SourceConfig(spec, enabled))

	specs = [source.spec for source in sources]
	duplicates = {spec.label for spec in specs if specs.count(spec) > 1}
	if duplicates:
		raise ValueError(f"Duplicate sources in {path}: {sorted(duplicates)}")
	if not sources:
		raise ValueError(f"No sources defined in {path}")
	return sources


class SourceCatalog:
	"""Sources re-read from the file on every job run, so enabling/disabling one needs no restart.

	An invalid file at startup is an error; later, the last valid version is kept and the error logged.
	"""

	def __init__(self, path: Optional[Path], validate: Callable[[Iterable[SearchSpec]], None]):
		self._path = path
		self._validate = validate
		self._lock = threading.Lock()
		self._sources = self._load()

	def enabled(self) -> list[SearchSpec]:
		with self._lock:
			try:
				self._sources = self._load()
			except (OSError, ValueError) as e:  # tomllib.TOMLDecodeError is a ValueError
				logger.error("Cannot reload sources (%s), keeping the previous list", e)
			return [source.spec for source in self._sources if source.enabled]

	def find(self, label: str) -> SearchSpec:
		"""A configured source by label; disabled ones too, for running them by hand."""
		spec = SearchSpec.from_label(label)
		if spec not in {source.spec for source in self._sources}:
			raise ValueError(f"Source {label!r} is not configured in {self._path or DEFAULT_SOURCES_FILE}")
		return spec

	def _load(self) -> list[SourceConfig]:
		sources = load_sources(self._path)
		self._validate(source.spec for source in sources)
		return sources
