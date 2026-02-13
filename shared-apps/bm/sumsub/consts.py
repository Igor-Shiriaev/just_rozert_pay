from enum import auto
from bm.common.entities import StrEnum


class SumSubFlowInitiator(StrEnum):
    USER = auto()
    SYSTEM = auto()


class LevelStatus(StrEnum):
    RED = 'RED'
    GREEN = 'GREEN'
    UNKNOWN = 'UNKNOWN'


class ActionType(StrEnum):
    BANK_CARD = 'bankCard'
    QUESTIONNAIRE = 'questionnaire'
    BANK_STATEMENT = 'bankStatement'


class SumSubFlowName(StrEnum):
    # Case sensitive
    basic_aml_level = 'basic-aml-level'
    basic_kyc_level = 'basic-kyc-level'
    basic_aml_level_mx = 'basic-aml-level-mx'
    initial_kyc_level_mx = 'initial-kyc-level-mx'
    basic_kyc_level_mx = 'basic-kyc-level-mx'
    initial_kyc_level_247bet_mx = 'initial-kyc-level-247bet-mx'
    basic_kyc_level_247bet_mx = 'basic-kyc-level-247bet-mx'
    basic_verification_level_uk = 'basic_verification_level_uk'
    basic_kyc_level_se = 'basic-kyc-level-se'
    basic_kyc_level_dk = 'basic-kyc-level-dk'
    basic_aml_level_mga = 'basic-aml-level-mga'
    basic_kyc_level_mga = 'basic-kyc-level-mga'
    basic_aml_level_iom = 'basic-aml-level-IOM'
    basic_kyc_level_iom = 'basic-kyc-level-IOM'
    sof_level_mga = 'sof-level-mga'
    sow_level_mga = 'SOW-level-mga'
    sof_level_iom = 'SOF-level-IOM'
    sow_level_iom = 'SOW-level-IOM'
    basic_aml_level_ee = 'basic-aml-level-ee'
    basic_kyc_level_ee = 'basic-kyc-level-ee'
    sow_level_ee = 'SOW_EE'
    cards_pop_level_ee = 'cards-pop-level-ee'
    cards_pop_level_mga = 'cards-pop-level-mga'
    cards_pop_level_uk = 'cards_pop_level_uk'
    basic_verification_level_ee = 'basic-verification-level-ee'
    rg_confirmation = 'RG_confirmation'
    sow_sof_questionnaire_mga = 'sow_sof_questionnaire_mga'
    sow_mga = 'sow_mga'
    sow_sof_questionnaire_cw = 'sow_sof_questionnaire_cw'
    sow_cw = 'sow_cw'
    sow_sof_questionnaire_iom = 'sow_sof_questionnaire_iom'
    sow_iom = 'sow_iom'
    kyc_full_level_mga = 'kyc_full_level_mga'
    kyc_full_level_rg_mga = 'kyc_full_level_rg_mga'
    sow_sof_questionnaire_rg_mga = 'sow_sof_questionnaire_rg_mga'
    sow_rg_mga = 'sow_rg_mga'
    basic_kyc_level_pe = 'basic_kyc_level_pe'
    basic_kyc_level_uk = 'basic_kyc_level_uk'
    basic_aml_level_pe = 'basic_aml_level_pe'
    kyc_full_level_uk = 'kyc_full_level_uk'
    sow_uk = 'sow_uk'
    kyc_third_party_pm_level_uk = 'kyc_third_party_pm_level_uk'  # same as POP
    kyc_duplicates_mt = 'kyc_duplicates_mt'
    kyc_duplicates_uk = 'kyc_duplicates_uk'
    basic_aml_level_co = 'basic_aml_level_co'
    basic_kyc_level_co = 'basic_kyc_level_co'
    kyc_full_level_iom = 'kyc_full_level_iom'
    cards_pop_level_iom = 'cards_pop_level_iom'
    pop_level_ee = 'pop_level_ee'
    basic_kyc_level_mz = 'basic-kyc-level-mz'

    test_basic_aml_level = 'test-basic-aml-level'
    test_basic_kyc_level = 'test-basic-kyc-level'
    test_basic_aml_level_mx = 'test-basic-aml-level-mx'
    test_initial_kyc_level_mx = 'test-initial-kyc-level-mx'
    test_basic_verification_level_uk = 'test-basic_verification_level_uk'
    test_basic_kyc_level_mx = 'test-basic-kyc-level-mx'
    test_initial_kyc_level_247bet_mx = 'test-initial-kyc-level-247bet-mx'
    test_basic_kyc_level_247bet_mx = 'test-basic-kyc-level-247bet-mx'
    test_basic_kyc_level_se = 'test-basic-kyc-level-se'
    test_basic_kyc_level_dk = 'test-basic-kyc-level-dk'
    test_basic_aml_level_mga = 'test-basic-aml-level-mga'
    test_basic_kyc_level_mga = 'test-basic-kyc-level-mga'
    test_basic_aml_level_iom = 'test-basic-aml-level-IOM'
    test_basic_kyc_level_iom = 'test-basic-kyc-level-IOM'
    test_sof_level_mga = 'test-sof-level-mga'
    test_sow_level_mga = 'test-SOW-level-mga'
    test_sof_level_iom = 'test-SOF-level-IOM'
    test_sow_level_iom = 'test-SOW-level-IOM'
    test_basic_aml_level_ee = 'test-basic-aml-level-ee'
    test_basic_kyc_level_ee = 'test-basic-kyc-level-ee'
    test_sow_level_ee = 'test-SOW_EE'
    test_cards_pop_level_ee = 'test-cards-pop-level-ee'
    test_cards_pop_level_mga = 'test-cards-pop-level-mga'
    test_cards_pop_level_uk = 'test-cards_pop_level_uk'
    test_basic_verification_level_ee = 'test-basic-verification-level-ee'
    test_rg_confirmation = 'test-RG_confirmation'
    test_sow_sof_questionnaire_mga = 'test-sow_sof_questionnaire_mga'
    test_sow_mga = 'test-sow_mga'
    test_sow_sof_questionnaire_cw = 'test-sow_sof_questionnaire_cw'
    test_sow_cw = 'test-sow_cw'
    test_sow_sof_questionnaire_iom = 'test-sow_sof_questionnaire_iom'
    test_sow_iom = 'test-sow_iom'
    test_kyc_full_level_mga = 'test-kyc_full_level_mga'
    test_kyc_full_level_rg_mga = 'test-kyc_full_level_rg_mga'
    test_sow_sof_questionnaire_rg_mga = 'test-sow_sof_questionnaire_rg_mga'
    test_sow_rg_mga = 'test-sow_rg_mga'
    test_basic_kyc_level_pe = 'test-basic_kyc_level_pe'
    test_basic_kyc_level_uk = 'test-basic_kyc_level_uk'
    test_basic_aml_level_pe = 'test-basic_aml_level_pe'
    test_kyc_full_level_uk = 'test-kyc_full_level_uk'
    test_sow_uk = 'test-sow_uk'
    test_kyc_third_party_pm_level_uk = 'test-kyc_third_party_pm_level_uk'
    test_kyc_duplicates_mt = 'test-kyc_duplicates_mt'
    test_kyc_duplicates_uk = 'test-kyc_duplicates_uk'
    test_basic_aml_level_co = 'test-basic_aml_level_co'
    test_basic_kyc_level_co = 'test-basic_kyc_level_co'
    test_kyc_full_level_iom = 'test-kyc_full_level_iom'
    test_cards_pop_level_iom = 'test-cards_pop_level_iom'
    test_pop_level_ee = 'test-pop_level_ee'
    test_basic_kyc_level_mz = 'test-basic-kyc-level-mz'


class SumSubSourceKey(StrEnum):
    curacao_axwin = 'curacao-axwin'
    curacao_betmaster = 'curacao-betmaster'
    curacao_bongo = 'curacao-bongo'
    curacao_casinoin = 'curacao-casinoin'
    curacao_genslot = 'curacao-genslot'
    curacao_mix4bet = 'curacao-mix4bet'
    curacao_betfree = 'curacao-betfree'
    dk_betmaster = 'dk-betmaster'
    ee_betmaster = 'ee-betmaster'
    iom_betmaster = 'iom-betmaster'
    mexico_betmaster = 'mexico-betmaster'
    mexico_casinoin = 'mexico-casinoin'
    mga_axwin = 'mga-axwin'
    mga_betmaster = 'mga-betmaster'
    mga_bongo = 'mga-bongo'
    mga_casinoin = 'mga-casinoin'
    mga_mix4bet = 'mga-mix4bet'
    mga_betfree = 'mga-betfree'
    se_betmaster = 'se-betmaster'
    uk_betmaster = 'uk-betmaster'
    ee_casinoin = 'ee-casinoin'
    pe_betmaster = 'pe-betmaster'
    co_betmaster = 'co-betmaster'
    mexico_247bet = 'mexico-247bet'
    mozambique_betmaster = 'mozambique-betmaster'


class SumSubFlowGroup(StrEnum):
    aml = auto()
    kyc = auto()
    cards_pop = auto()
    independent = auto()
    rg_confirmation = auto()
    sow = auto()
    sof = auto()
    kyc_additional = auto()


class VerificationStep(StrEnum):
    QUESTIONNAIRE = 'QUESTIONNAIRE'


class VerificationGeneralStatus(StrEnum):
    initial = auto()
    pending = auto()
    successful = auto()
    failed = auto()


class VerificationRequestReason(StrEnum):
    FIRST_WITHDRAWAL = auto()
