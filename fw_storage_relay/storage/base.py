# Copyright (c) 2026, Flowwolf Inc. and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Protocol


class StorageBackend(Protocol):
	def upload(self, key: str, content: bytes, *, content_type: str | None = None, public: bool = False) -> None:
		...

	def download(self, key: str) -> bytes:
		...

	def delete(self, key: str) -> None:
		...

	def exists(self, key: str) -> bool:
		...

	def get_public_url(self, key: str) -> str:
		...

	def get_presigned_url(self, key: str, expiry: int) -> str:
		...
