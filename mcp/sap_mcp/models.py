from typing import TypedDict


class PetSummary(TypedDict):
    slug: str
    name: str
    tier: int
    attack: int
    health: int
    trigger: str
    rollable: bool
    types: list[str]


class Pet(TypedDict):
    slug: str
    name: str
    tier: int
    cost: int
    attack: int
    health: int
    rollable: bool
    trigger: str
    ability1: str
    ability2: str
    ability3: str
    types: list[str]


class FoodSummary(TypedDict):
    slug: str
    name: str
    tier: int
    rollable: bool


class Food(TypedDict):
    slug: str
    name: str
    tier: int
    cost: int
    rollable: bool
    ability: str


class ToySummary(TypedDict):
    slug: str
    name: str
    tier: int
    trigger: str
    rollable: bool


class Toy(TypedDict):
    slug: str
    name: str
    tier: int
    cost: int
    attack: int
    health: int
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
