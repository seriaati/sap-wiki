import os
import pathlib

GAME_DIR = str(pathlib.Path.home() / ".local/share/Steam/steamapps/common/Super Auto Pets")
GAME_BIN = f"{GAME_DIR}/superautopets.x86_64"

BUNDLE_DIR_RELATIVE = os.path.join(
    "ExportedProject", "Assets", "StreamingAssets", "aa", "StandaloneLinux64"
)
SHARED_BUNDLE_NAME = "localization-assets-shared_assets_all.bundle"
ENGLISH_STRINGS_BUNDLE_NAME = "localization-string-tables-english_assets_all.bundle"
EXPORTED_ASSETS_RELATIVE = os.path.join("ExportedProject", "Assets")
TEXTURE2D_DIR_RELATIVE = os.path.join("ExportedProject", "Assets", "Texture2D")

TRIG_CLASS_TO_LOCO = {
    "TriggerSell": "BeforeSell",
    "TriggerBeforeSell": "BeforeSell",
    "TriggerUpgradeShopTier": "ShopUpgrade",
    "TriggerRoll": "ShopRolled",
    "TriggerStartBattle": "StartBattle",
    "TriggerBeforeStartBattle": "BeforeStartBattle",
    "TriggerStartTurn": "StartTurn",
    "TriggerEndTurn": "EndTurn",
    "TriggerDeath": "ThisDied",
    "TriggerBeforeDeath": "BeforeThisDies",
    "TriggerDeathEarly": "BeforeThisDies",
    "TriggerAllEnemiesFaint": "AllEnemiesDied",
    "TriggerAllFriendsFaint": "AllFriendsFainted",
    "TriggerHurt": "ThisHurt",
    "TriggerHurtEarly": "ThisHurt",
    "TriggerAttack": "AnyoneAttack",
    "TriggerBeforeAttack": "BeforeThisAttacks",
    "TriggerKill": "ThisKilled",
    "TriggerSummon": "ThisSummoned",
    "TriggerPlayMinion": "OtherSummoned",
    "TriggerTransform": "ThisTransformed",
    "TriggerEmptyFriendlyFront": "ClearFront",
    "TriggerFlung": "AnyoneFlung",
    "TriggerPushed": "EnemyPushed",
    "TriggerPerkGained": "ThisGainedPerk",
    "TriggerPerkLost": "ThisLostPerk",
    "TriggerLevelup": "ThisLeveledUp",
    "TriggerExpGained": "GainExp",
    "TriggerCharged": "Charged",
    "TriggerManaGained": "ThisGainedMana",
    "TriggerPlaySpell": "PlaySpell",
    "TriggerPlayedSpellOn": "PlayedSpellOn",
    "TriggerComposite": "Composite",
}
