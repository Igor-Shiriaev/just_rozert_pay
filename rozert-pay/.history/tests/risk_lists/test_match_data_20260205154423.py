from rozert_pay.risk_lists.const import MatchFieldKey, scope
from rozert_pay.risk_lists.services.match_data import MatchData
from tests.risk_lists.factories import GrayListEntryFactory


class TestMatchData:
    def test_match_data_and_vs_or_logic(self):
        md = MatchData(
            customer_id=None,
            email="user@x.com",
            phone="123",
            customer_name=None,
            masked_pan=None,
            customer_wallet_id=None,
            ip=None,
            provider_code=None,
        )

        e_global = GrayListEntryFactory.build(
            participation_type=scope.GLOBAL,
            customer=None,
            email="user@x.com",
            phone="wrong",
            match_fields=[MatchFieldKey.EMAIL.value, MatchFieldKey.PHONE.value],
        )
        assert md.matches(e_global) is False

        e_merchant = GrayListEntryFactory.build(
            participation_type=scope.MERCHANT,
            email="user@x.com",
            phone="wrong",
            match_fields=[MatchFieldKey.EMAIL.value, MatchFieldKey.PHONE.value],
        )
        assert md.matches(e_merchant) is True

    def test_match_data_normalizes_strings(self):
        md = MatchData(
            customer_id=None,
            email="  User@Example.COM  ",
            phone=None,
            customer_name=None,
            masked_pan=None,
            customer_wallet_id=None,
            ip=None,
            provider_code=None,
        )

        e = GrayListEntryFactory.build(
            participation_type=scope.GLOBAL,
            customer=None,
            email="user@example.com",
            match_fields=[MatchFieldKey.EMAIL.value],
        )
        assert md._is_field_match(e, MatchFieldKey.EMAIL) is True

    def test_match_data_customer_id_logic(self):
        md_user = MatchData(
            customer_id=100,
            email="new_email@x.com",
            phone=None,
            customer_name=None,
            masked_pan=None,
            customer_wallet_id=None,
            ip=None,
            provider_code=None,
        )

        e_merchant = GrayListEntryFactory.build(
            participation_type=scope.MERCHANT,
            customer__id=100,
            email="old_email@x.com",
            match_fields=[MatchFieldKey.EMAIL.value],
        )
        assert md_user.matches(e_merchant) is True

        md_other = MatchData(
            customer_id=200,
            email="bad@x.com",
            phone=None,
            customer_name=None,
            masked_pan=None,
            customer_wallet_id=None,
            ip=None,
            provider_code=None,
        )

        e_merchant_multi = GrayListEntryFactory.build(
            participation_type=scope.MERCHANT,
            customer__id=100,
            email="bad@x.com",
            match_fields=[MatchFieldKey.EMAIL.value],
        )
        assert md_other.matches(e_merchant_multi) is True
