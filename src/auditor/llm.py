"""Thin client for Muse Spark on the Meta Model API (OpenAI-compatible endpoint)."""
from __future__ import annotations

import copy
import os

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel

from .data import ROOT

META_BASE_URL = "https://api.meta.ai/v1"
BASETEN_BASE_URL = "https://inference.baseten.co/v1"
# Muse Spark Open (open weights) served by Baseten. The participant guide names
# "meta-models/muse-spark-open-1026"; accounts without the hackathon grant list the slug below.
# Override with OPEN_MODEL in .env.
OPEN_MODEL_DEFAULT = "meta-models/muse-spark-open"


def open_model() -> str:
    load_dotenv(ROOT / ".env")
    return os.environ.get("OPEN_MODEL", OPEN_MODEL_DEFAULT)


def get_client() -> OpenAI:
    load_dotenv(ROOT / ".env")
    key = os.environ.get("MODEL_API_KEY")
    if not key:
        raise RuntimeError("MODEL_API_KEY is not set. Copy .env.example to .env and add your key.")
    return OpenAI(base_url=META_BASE_URL, api_key=key)


def get_baseten_client() -> OpenAI:
    load_dotenv(ROOT / ".env")
    key = os.environ.get("BASETEN_API_KEY")
    if not key:
        raise RuntimeError("BASETEN_API_KEY is not set. Add it to .env.")
    return OpenAI(base_url=BASETEN_BASE_URL, api_key=key)


def default_model() -> str:
    load_dotenv(ROOT / ".env")
    return os.environ.get("MUSE_MODEL", "muse-spark-1.3")


def api_schema(model: type[BaseModel]) -> dict:
    """JSON schema for response_format: $refs inlined, every property required,
    no extra properties. (Strict structured-output modes commonly require this.)"""
    schema = model.model_json_schema()
    defs = schema.pop("$defs", {})

    def resolve(node):
        if isinstance(node, dict):
            if "$ref" in node:
                return resolve(copy.deepcopy(defs[node["$ref"].split("/")[-1]]))
            node = {k: resolve(v) for k, v in node.items() if k not in ("default", "title")}
            if node.get("type") == "object" and "properties" in node:
                node["required"] = list(node["properties"])
                node["additionalProperties"] = False
            return node
        if isinstance(node, list):
            return [resolve(v) for v in node]
        return node

    return resolve(schema)


def response_format(model: type[BaseModel], name: str) -> dict:
    return {"type": "json_schema", "json_schema": {"name": name, "strict": True, "schema": api_schema(model)}}
