# Copyright (c) 2026, Flowwolf Inc. and contributors
# For license information, please see license.txt

from __future__ import annotations

import boto3
from botocore.exceptions import ClientError

from fw_storage_relay.config import get_s3_config


class S3Backend:
	def __init__(self, config: dict | None = None):
		self.config = config or get_s3_config()
		if not self.config:
			raise ValueError("S3 configuration is missing from site_config.json")

		self.bucket = self.config["bucket"]
		self.region = self.config["region"]
		self._client = boto3.client(
			"s3",
			aws_access_key_id=self.config["access_key"],
			aws_secret_access_key=self.config["secret_key"],
			region_name=self.region,
		)

	def upload(self, key: str, content: bytes, *, content_type: str | None = None, public: bool = False) -> None:
		extra_args = {}
		if content_type:
			extra_args["ContentType"] = content_type
		if public:
			extra_args["ACL"] = "public-read"

		self._client.put_object(Bucket=self.bucket, Key=key, Body=content, **extra_args)
		self._client.head_object(Bucket=self.bucket, Key=key)

	def download(self, key: str) -> bytes:
		response = self._client.get_object(Bucket=self.bucket, Key=key)
		return response["Body"].read()

	def delete(self, key: str) -> None:
		self._client.delete_object(Bucket=self.bucket, Key=key)

	def exists(self, key: str) -> bool:
		try:
			self._client.head_object(Bucket=self.bucket, Key=key)
			return True
		except ClientError:
			return False

	def get_public_url(self, key: str) -> str:
		return f"https://{self.bucket}.s3.{self.region}.amazonaws.com/{key}"

	def get_presigned_url(self, key: str, expiry: int) -> str:
		return self._client.generate_presigned_url(
			"get_object",
			Params={"Bucket": self.bucket, "Key": key},
			ExpiresIn=expiry,
		)
