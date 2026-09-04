"""Turns one `TemplateVersion.extraction_categories[i]` JSON definition
into the same triple `app.intelligence.schemas.EXTRACTION_CATEGORIES`
values already are: `(wrapper_schema_cls, item_field_name, fact_type)`,
plus the LLM instruction text for that category.

Two paths, both real (neither is a stub):

- `builtin: true` entries resolve directly to the existing, unchanged
  `app.intelligence.schemas.EXTRACTION_CATEGORIES` / `_CATEGORY_INSTRUCTIONS`
  — this is what keeps the "General Conversation" template byte-for-byte
  behaviorally identical to Phase 4/5 (same Pydantic classes, same field
  constraints, same validation errors), never a reimplementation that
  could silently drift.
- Everything else is built dynamically via `pydantic.create_model` from
  the category's `fields` list — this is what makes "Meeting" (and the
  Medical/Psychotherapy foundation templates) a genuine, independently
  defined category, not builtin at all.

Every dynamically-built item schema always carries `certainty` (the same
`app.intelligence.schemas.Certainty` enum) and `evidence_segment_sequences`
— the same evidence-citation contract every category must honor (see
app.intelligence.service._resolve_evidence), so a template author can add
a new category without needing to re-implement evidence linking.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pydantic
from pydantic import Field, create_model

from app.intelligence.prompts import get_builtin_category_instruction
from app.intelligence.schemas import EXTRACTION_CATEGORIES, Certainty


@dataclass(frozen=True, slots=True)
class ResolvedCategory:
    key: str
    fact_type: str
    item_field: str
    schema_cls: type[pydantic.BaseModel]
    instruction: str


class InvalidCategoryDefinitionError(ValueError):
    pass


def _build_dynamic_schema(category_def: dict[str, Any]) -> type[pydantic.BaseModel]:
    key = category_def["key"]
    item_field = category_def["item_field"]
    fields_def = category_def.get("fields", [])
    if not fields_def:
        raise InvalidCategoryDefinitionError(f"category {key!r} defines no fields")

    item_fields: dict[str, Any] = {}
    for field_def in fields_def:
        name = field_def["name"]
        max_length = field_def.get("max_length", 1024)
        description = field_def.get("description")
        item_fields[name] = (
            str,
            Field(max_length=max_length, description=description),
        )
    item_fields["certainty"] = (Certainty, Field())
    item_fields["evidence_segment_sequences"] = (
        list[int],
        Field(default_factory=list),
    )

    item_model: type[pydantic.BaseModel] = create_model(f"{key}_Item", **item_fields)
    wrapper_fields: dict[str, Any] = {
        item_field: (list[item_model], Field(default_factory=list))  # type: ignore[valid-type]
    }
    wrapper_model: type[pydantic.BaseModel] = create_model(f"{key}_Extraction", **wrapper_fields)
    return wrapper_model


def resolve_category(category_def: dict[str, Any]) -> ResolvedCategory:
    key = category_def["key"]
    if category_def.get("builtin"):
        if key not in EXTRACTION_CATEGORIES:
            raise InvalidCategoryDefinitionError(
                f"category {key!r} marked builtin but is not one of "
                f"{sorted(EXTRACTION_CATEGORIES)}"
            )
        schema_cls, item_field, fact_type = EXTRACTION_CATEGORIES[key]
        instruction = category_def.get("instruction") or get_builtin_category_instruction(key)
        return ResolvedCategory(
            key=key,
            fact_type=fact_type,
            item_field=item_field,
            schema_cls=schema_cls,
            instruction=instruction,
        )

    fact_type = category_def.get("fact_type", key)
    item_field = category_def.get("item_field", "items")
    instruction = category_def["instruction"]
    schema_cls = _build_dynamic_schema(category_def)
    return ResolvedCategory(
        key=key, fact_type=fact_type, item_field=item_field, schema_cls=schema_cls,
        instruction=instruction,
    )


def resolve_categories(category_defs: list[dict[str, Any]]) -> list[ResolvedCategory]:
    return [resolve_category(c) for c in category_defs]
