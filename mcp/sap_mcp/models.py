from typing import TypedDict


class PetSummary(TypedDict):
    key: str
    slug: str
    name: str
    tier: int
    attack: int
    health: int
    trigger: str
    rollable: bool
    types: list[str]


class Pet(TypedDict):
    key: str
    slug: str
    name: str
    tier: int
    cost: int
    attack: int
    health: int
    active: bool
    rollable: bool
    trigger: str
    ability1: str
    ability2: str
    ability3: str
    types: list[str]


class FoodSummary(TypedDict):
    key: str
    slug: str
    name: str
    tier: int
    rollable: bool


class Food(TypedDict):
    key: str
    slug: str
    name: str
    tier: int
    cost: int
    active: bool
    rollable: bool
    ability: str


class ToySummary(TypedDict):
    key: str
    slug: str
    name: str
    tier: int
    trigger: str
    rollable: bool


class Toy(TypedDict):
    key: str
    slug: str
    name: str
    tier: int
    cost: int
    attack: int
    health: int
    active: bool
    rollable: bool
    trigger: str
    ability1: str
    ability2: str
    ability3: str


class SearchResult(TypedDict):
    kind: str
    slug: str
    name: str
    snippet: str


class SearchDoc(TypedDict):
    kind: str
    slug: str
    name: str
    text: str
