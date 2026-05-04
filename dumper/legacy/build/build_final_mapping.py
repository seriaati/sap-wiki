"""
Build final ability→trigger mapping from Frida dump + localization data.

Input:  trigger_mapping_frida.json  (Frida runtime dump)
        sap_ability_data.json       (localization: abilities, triggers, pet names)
Output: ability_trigger_map.json
"""
import json

# TriggerMinions subclass name → localization trigger key
TRIG_CLASS_TO_LOCO = {
    # Sell/Shop
    'TriggerSell':              'BeforeSell',
    'TriggerBeforeSell':        'BeforeSell',
    'TriggerUpgradeShopTier':   'ShopUpgrade',
    'TriggerRoll':              'ShopRolled',
    # Battle start
    'TriggerStartBattle':       'StartBattle',
    'TriggerBeforeStartBattle': 'BeforeStartBattle',
    # Turn
    'TriggerStartTurn':         'StartTurn',
    'TriggerEndTurn':           'EndTurn',
    # Death
    'TriggerDeath':             'ThisDied',
    'TriggerBeforeDeath':       'BeforeThisDies',
    'TriggerDeathEarly':        'BeforeThisDies',
    'TriggerAllEnemiesFaint':   'AllEnemiesDied',
    'TriggerAllFriendsFaint':   'AllFriendsFainted',
    # Hurt
    'TriggerHurt':              'ThisHurt',
    'TriggerHurtEarly':         'ThisHurt',
    # Attack
    'TriggerAttack':            'AnyoneAttack',
    'TriggerBeforeAttack':      'BeforeThisAttacks',
    'TriggerKill':              'ThisKilled',
    # Summon/Transform
    'TriggerSummon':            'ThisSummoned',
    'TriggerPlayMinion':        'OtherSummoned',
    'TriggerTransform':         'ThisTransformed',
    'TriggerEmptyFriendlyFront':'ClearFront',
    'TriggerFlung':             'AnyoneFlung',
    'TriggerPushed':            'EnemyPushed',
    # Perk/Level
    'TriggerPerkGained':        'ThisGainedPerk',
    'TriggerPerkLost':          'ThisLostPerk',
    'TriggerLevelup':           'ThisLeveledUp',
    'TriggerExpGained':         'GainExp',
    # Misc
    'TriggerCharged':           'Charged',         # no exact loco key
    'TriggerManaGained':        'ThisGainedMana',
    'TriggerPlaySpell':         'PlaySpell',        # no exact loco key
    'TriggerPlayedSpellOn':     'PlayedSpellOn',    # no exact loco key
    'TriggerComposite':         'Composite',
}


def main():
    with open('trigger_mapping_frida.json') as f:
        frida_data = json.load(f)
    with open('sap_ability_data.json') as f:
        loco = json.load(f)

    triggers_loco = loco['triggers']    # loco_key → {'' : display}
    abilities_loco = loco['abilities']  # AbilityName → {level.field : text}
    pet_names = loco['pet_names']       # PetName → display name

    # Derive pet name from ability name (BeaverAbility → Beaver)
    def pet_from_ability(ability_name: str) -> str:
        if ability_name.endswith('Ability'):
            return ability_name[:-7]
        return ability_name

    result = {}
    unmapped = []

    for ability, trig_cls in frida_data['trigger_map'].items():
        loco_key = TRIG_CLASS_TO_LOCO.get(trig_cls)

        if loco_key and loco_key in triggers_loco:
            display = triggers_loco[loco_key].get('', loco_key)
        elif trig_cls and trig_cls != 'RectTransform':
            # Strip "Trigger" prefix as fallback display
            display = trig_cls[7:] if trig_cls.startswith('Trigger') else trig_cls
            unmapped.append(trig_cls)
        else:
            display = None  # RectTransform garbage

        pet = pet_from_ability(ability)
        pet_display = pet_names.get(pet, '')

        # Gather ability descriptions from localization
        ab_loco = abilities_loco.get(ability, {})

        result[ability] = {
            'pet': pet,
            'pet_display': pet_display,
            'trigger_class': trig_cls,
            'trigger_loco_key': loco_key,
            'trigger_display': display,
            'ability_1': ab_loco.get('1.About', ''),
            'ability_2': ab_loco.get('2.About', ''),
            'ability_3': ab_loco.get('3.About', ''),
        }

    with open('ability_trigger_map.json', 'w') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f'Written {len(result)} abilities to ability_trigger_map.json')
    if unmapped:
        print(f'Trigger classes without loco key (used class name): {sorted(set(unmapped))}')

    # Print sample
    print()
    print(f'{"Ability":45s} {"Trigger":30s} Pet')
    print('-' * 90)
    for k, v in sorted(result.items())[:30]:
        print(f'{k:45s} {(v["trigger_display"] or "?"):30s} {v["pet_display"]}')


if __name__ == '__main__':
    main()
