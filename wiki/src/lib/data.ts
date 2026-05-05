import petsRaw from '@data/pets.json'
import foodsRaw from '@data/foods.json'
import toysRaw from '@data/toys.json'

export interface Pet {
  key: string
  slug: string
  name: string
  tier: number
  cost: number
  attack: number
  health: number
  active: boolean
  rollable: boolean
  trigger: string
  ability1: string
  ability2: string
  ability3: string
  image: string
  imageLegacy: string
  types: string[]
}

export interface Food {
  key: string
  slug: string
  name: string
  tier: number
  cost: number
  active: boolean
  rollable: boolean
  ability: string
  image: string
  imageLegacy: string
}

export const pets: Pet[] = Object.entries(
  petsRaw as Record<string, Omit<Pet, 'key' | 'slug'>>
).map(([key, pet]) => ({
  key,
  slug: key.toLowerCase(),
  ...pet,
}))

export const foods: Food[] = Object.entries(
  foodsRaw as Record<string, Omit<Food, 'key' | 'slug'>>
).map(([key, food]) => ({
  key,
  slug: key.toLowerCase(),
  ...food,
}))

export interface Toy {
  key: string
  slug: string
  name: string
  tier: number
  cost: number
  attack: number
  health: number
  active: boolean
  rollable: boolean
  trigger: string
  ability1: string
  ability2: string
  ability3: string
  image: string
  imageLegacy: string
}

export const toys: Toy[] = Object.entries(
  toysRaw as Record<string, Omit<Toy, 'key' | 'slug'>>
).map(([key, toy]) => ({
  key,
  slug: key.toLowerCase(),
  ...toy,
}))
