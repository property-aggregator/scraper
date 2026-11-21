from dataclasses import dataclass, field
from typing import Mapping, Optional


@dataclass(frozen=True)
class FetchResult:
	"""Outcome of an HTTP GET. Never raised: callers decide what a status means."""

	requested_url: str
	url: str  # final URL after redirects
	status: Optional[int]  # None = network error
	content: bytes = b""
	headers: Mapping[str, str] = field(default_factory=dict)
	error: Optional[str] = None

	@property
	def ok(self) -> bool:
		return self.status is not None and 200 <= self.status < 300

	@property
	def blocked(self) -> bool:
		return self.status in (403, 429)

	@property
	def retriable(self) -> bool:
		# 403/404 do not change on retry; network errors, 429 and 5xx might.
		return self.status is None or self.status == 429 or self.status >= 500

	@property
	def redirected(self) -> bool:
		return self.url != self.requested_url

	@property
	def text(self) -> str:
		return self.content.decode("utf-8", errors="replace")

	def describe(self) -> str:
		if self.status is None:
			return f"network error: {self.error}"
		retry_after = self.headers.get("retry-after")
		return f"HTTP {self.status}" + (f" (retry-after={retry_after})" if retry_after else "")


class FetchError(Exception):
	"""Raised by scrapers when a page they need could not be fetched."""

	def __init__(self, result: FetchResult):
		super().__init__(f"{result.requested_url}: {result.describe()}")
		self.result = result
