from bm.common.entities import StrEnum


class CasinoProviderType(StrEnum):
    XPRESSGAMING = 'X'
    SLOTEGRATOR = 'S'
    SLOTEGRATOR2 = 'S2'
    HUB88 = 'H'
    ST8 = 'ST'
    SOFTGAMING = 'SG'
    PLAYNGO = 'PG'
    NETENT = 'NET'
    PRAGMATICPLAY = 'PP'
    PRAGMATICPLAY_ASIA = 'PPA'
    PRAGMATICPLAY_BINGO = 'PPB'
    EVOPLAY = 'EP'
    SPADEGAMING = 'SPG'
    MICROGAMING = 'MG'
    YGGDRASIL = 'Y'
    BOOONGO = 'BNG'
    PGSOFT = 'PGS'
    MANNAPLAY = 'MP'
    SPINOMENAL = 'SPML'
    OUTCOMEBET = 'OBET'
    TWOWP = 'TWP'
    B2B_SLOTS = 'B2BS'
    EVOLUTION = 'EV'
    ZITRO = 'Z'
    GO_PLUS = 'GP'
    RELAX = 'RX'
    SA_GAMING = 'SGM'
    CASINO2B = 'C2B'
    PLAYTECH = 'PT'
    TORRERO = 'TRR'

    @property
    def name_low(self) -> str:
        return self.name.lower()

    @property
    def name_as_classname(self) -> str:
        return self.name_low.replace('_', ' ').title().replace(' ', '')


OBSOLETE_CASINO_PROVIDER_TYPES = [
    CasinoProviderType.CASINO2B,
]


ACTIVE_CASINO_PROVIDER_TYPES = [
    casino_provider_type
    for casino_provider_type in CasinoProviderType
    if casino_provider_type not in OBSOLETE_CASINO_PROVIDER_TYPES
]


FREESPIN_LIMITS_BY_CURRENCY = {'XBT_PN6': 100000}
