from __future__ import annotations
from datetime import datetime, timezone
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, model_validator


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

class Price(BaseModel):
    amount: float | None = None
    currency: str | None = None
    source: str | None = None
    url: str | None = None
    retrieved_at: str | None = None
    converted: bool = False
    original_amount: float | None = None
    original_currency: str | None = None
    condition_assumed: str | None = None
    match_confidence: float | None = Field(default=None, ge=0, le=1)
    unavailable_reason: str | None = None

    @model_validator(mode='after')
    def source_required(self):
        if self.amount is not None and (not self.url or not self.source or not self.currency or not self.retrieved_at):
            raise ValueError('Non-null price requires a named source, currency, source URL and retrieval time')
        if self.url is not None and not self.url.startswith('https://'):
            raise ValueError('Price evidence URL must use HTTPS')
        if self.amount is not None and self.amount < 0:
            raise ValueError('Negative price')
        return self

class PriceRange(BaseModel):
    low: float | None = None
    high: float | None = None
    currency: str | None = None
    source: str | None = None
    url: str | None = None
    retrieved_at: str | None = None
    unavailable_reason: str | None = None

    @model_validator(mode='after')
    def validate_range(self):
        if (self.low is None) != (self.high is None):
            raise ValueError('Both endpoints of a price range must be supplied together')
        if self.url is not None and not self.url.startswith('https://'):
            raise ValueError('Range evidence URL must use HTTPS')
        if self.low is not None:
            if self.low < 0 or self.high < self.low:
                raise ValueError('Invalid range')
            if not (self.url and self.source and self.currency and self.retrieved_at):
                raise ValueError('Sourced range requires metadata')
        return self

class Measurement(BaseModel):
    value: float | None = Field(default=None, ge=0)
    unit: str
    method: str | None = None
    frame_refs: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0, ge=0, le=1)
    uncertainty: float | None = Field(default=None, ge=0)

class Book(BaseModel):
    id: str
    shelf: str
    position: int = Field(ge=0)
    frame_ref: str
    status: Literal['identified','unidentified','needs_appraisal'] = 'unidentified'
    title: str | None = None
    author: str | None = None
    publisher: str | None = None
    edition: str | None = None
    isbn: str | None = None
    spine_height_cm: float | None = None
    spine_thickness_cm: float | None = None
    height_measurement: Measurement | None = None
    thickness_measurement: Measurement | None = None
    id_confidence: float = Field(default=0, ge=0, le=1)
    measurement_confidence: float = Field(default=0, ge=0, le=1)
    valuation_confidence: float = Field(default=0, ge=0, le=1)
    replacement_cost: Price = Field(default_factory=Price)
    used_value: Price = Field(default_factory=Price)
    bbox: list[int] | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    detection_source: str = 'unknown'
    ocr_text: str | None = None
    notes: list[str] = Field(default_factory=list)
    excluded: bool = False

class Item(BaseModel):
    id: str
    category: str
    description: str
    brand_model: str | None = None
    frame_ref: str
    dimensions_cm: dict[str, float | None] = Field(default_factory=lambda: {'w':None,'h':None,'d':None})
    dimension_measurements: dict[str, Measurement] = Field(default_factory=dict)
    status: Literal['priced','range','needs_appraisal'] = 'needs_appraisal'
    replacement_cost: PriceRange = Field(default_factory=PriceRange)
    confidence: float = Field(default=0, ge=0, le=1)
    bbox: list[int] | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    excluded: bool = False
    notes: list[str] = Field(default_factory=list)

class Sweep(BaseModel):
    id: str
    captured_at: str
    device: str
    duration_s: float = Field(default=0, ge=0)
    country: str
    currency: str
    finished_at: str | None = None

class Room(BaseModel):
    length_m: float | None = Field(default=None, gt=0)
    width_m: float | None = Field(default=None, gt=0)
    height_m: float | None = Field(default=None, gt=0)
    floor_area_m2: float | None = None
    floor_area_ft2: float | None = None
    wall_area_m2: float | None = None
    wall_area_ft2: float | None = None
    shelved_wall_area_m2: float | None = None
    scale_method: str | None = None
    shape: str | None = None
    confidence: float = Field(default=0, ge=0, le=1)
    uncertainty: str | None = 'Not measured'
    geometry_evidence_refs: list[str] = Field(default_factory=list)

class Totals(BaseModel):
    book_count: int = 0
    books_identified: int = 0
    books_unidentified: int = 0
    shelf_run_m: float | None = None
    books_replacement_cost: float = 0
    books_used_value: float = 0
    items_replacement_cost_low: float = 0
    items_replacement_cost_high: float = 0
    excluded_from_totals: int = 0
    unpriced_books: int = 0
    unpriced_items: int = 0
    currency: str

class Review(BaseModel):
    ref_id: str
    reason: str

class Packet(BaseModel):
    model_config = ConfigDict(extra='forbid')
    sweep: Sweep
    room: Room
    books: list[Book]
    items: list[Item]
    totals: Totals
    review_queue: list[Review]
    stage_timings_ms: dict[str,float] = Field(default_factory=dict)
    stage_api_calls: dict[str,int] = Field(default_factory=dict)
    cost: dict = Field(default_factory=lambda:{'measured_usd':None,'estimated_usd':None,'reason':'Provider usage and pricing not available'})
    warnings: list[str] = Field(default_factory=list)
    audit_log: list[dict] = Field(default_factory=list)
