from datetime import datetime, timezone
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class Credentials(Strict):
    email: str = Field(min_length=5, max_length=254, pattern=r'^[^\s@]+@[^\s@]+\.[^\s@]+$')
    password: str = Field(min_length=12, max_length=128)

    @field_validator('email')
    @classmethod
    def normalize(cls, value):
        return value.casefold()

    @field_validator('password', mode='before')
    @classmethod
    def preserve_password(cls, value):
        # Whitespace is part of a password; forbid rather than silently change it.
        if isinstance(value, str) and value != value.strip():
            raise ValueError('Password cannot begin/end with whitespace')
        return value


class Reservation(Strict):
    product_id: str = Field(pattern=r'^[a-f0-9-]{36}$')
    quantity: int = Field(ge=1, le=10, strict=True)


class Pickup(Strict):
    code: str = Field(pattern=r'^[A-F0-9]{12}$')


class Favorite(Strict):
    enabled: bool


class DeleteAccount(Strict):
    password: str = Field(min_length=12, max_length=128)
    confirm: Literal['DELETE']


class Review(Strict):
    rating: int = Field(ge=1, le=5, strict=True)
    body: str = Field(min_length=1, max_length=1000)


class Store(Strict):
    owner_id: str = Field(pattern=r'^[a-f0-9-]{36}$')
    name: str = Field(min_length=1, max_length=100)
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)


class Deadline(Strict):
    @field_validator('pickup_deadline', 'expires_at', check_fields=False)
    @classmethod
    def utc_datetime(cls, value):
        if value.tzinfo is None:
            raise ValueError('Timestamp must include timezone')
        return value.astimezone(timezone.utc).replace(tzinfo=None)


class Product(Deadline):
    store_id: str = Field(pattern=r'^[a-f0-9-]{36}$')
    name: str = Field(min_length=1, max_length=160)
    photo_url: str = Field(max_length=2048, pattern=r'^https://[^\s]+$')
    original_price_minor: int = Field(ge=0, le=100000000, strict=True)
    sale_price_minor: int = Field(ge=0, le=100000000, strict=True)
    available_quantity: int = Field(ge=0, le=1000000, strict=True)
    pickup_deadline: datetime
    active: bool = True
    revision: int = Field(default=1, ge=1, strict=True)

    @model_validator(mode='after')
    def prices(self):
        if self.sale_price_minor > self.original_price_minor:
            raise ValueError('Sale price exceeds original price')
        return self


class Prize(Deadline):
    name: str = Field(min_length=1, max_length=120)
    kind: Literal['coupon','physical']
    weight: int = Field(ge=1, le=1000000, strict=True)
    remaining: int = Field(ge=0, le=1000000, strict=True)
    enabled: bool = False
    expires_at: datetime
    terms: str = Field(min_length=10, max_length=2000)
    discount_percent: Literal[20] | None = None

    @model_validator(mode='after')
    def coupon_rule(self):
        if (self.kind == 'coupon') != (self.discount_percent == 20):
            raise ValueError('Coupon must be 20 percent off; physical prize has no discount')
        return self


class Grant(Deadline):
    user_id: str = Field(pattern=r'^[a-f0-9-]{36}$')
    source_key: str = Field(min_length=8, max_length=120, pattern=r'^manual:[a-zA-Z0-9:_.-]+$')
    remaining: int = Field(ge=1, le=100, strict=True)
    expires_at: datetime


class ExpRule(Strict):
    event: Literal['pickup','review','favorite']
    amount: int = Field(ge=0, le=100000, strict=True)
    enabled: bool


class RankRule(Strict):
    start_rank: int = Field(ge=1, le=10000, strict=True)
    end_rank: int = Field(ge=1, le=10000, strict=True)
    spins: int = Field(ge=1, le=100, strict=True)


class RankingRules(Strict):
    rules: list[RankRule] = Field(min_length=1, max_length=20)

    @model_validator(mode='after')
    def no_overlap(self):
        previous = 0
        for rule in self.rules:
            if rule.start_rank <= previous or rule.end_rank < rule.start_rank:
                raise ValueError('Ranking ranges must be ordered and nonoverlapping')
            previous = rule.end_rank
        return self
