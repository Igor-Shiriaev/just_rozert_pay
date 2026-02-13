from enum import StrEnum, auto


class ComplianceMessageGroup(StrEnum):
    uk_continuous_play_flow = auto()
    expired_self_exclusion_flow = auto()
    deposit_sum_flow_to_make_deposit_limit = auto()
    deposit_count_flow_to_make_deposit_limit = auto()
    net_loss_flow_to_make_deposit_limit = auto()
    transactions_review_reminder_flow = auto()
    loss_complaint_flow_low_score = auto()
    loss_complaint_flow_high_score = auto()


class ComplianceMessageStep(StrEnum):
    reality_check_on_180_min = auto()
    reality_check_on_210_min = auto()
    reality_check_on_240_min = auto()
    notify_about_expired_self_exclusion = auto()
    deposit_sum_500_in_24_hours = auto()
    deposit_sum_1500_in_24_hours = auto()
    deposit_sum_2000_in_24_hours = auto()  # deprecated
    deposit_sum_2200_in_24_hours = auto()
    deposit_count_5_in_24_hours = auto()
    deposit_count_10_and_sum_1500_in_24_hours = auto()
    deposit_count_15_in_24_hours = auto()
    net_loss_1000_in_24_hours = auto()
    net_loss_1500_in_24_hours = auto()
    net_loss_2000_in_24_hours = auto()
    remind_to_review_transactions = auto()
    questionnaire_submitted_low_score = auto()
    questionnaire_submitted_high_score = auto()
