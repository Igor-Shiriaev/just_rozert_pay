import pytest
from django.contrib import admin
from django.contrib.admin.sites import AdminSite
from django.contrib.messages import get_messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory
from django.urls import reverse
from rozert_pay.account.models import User
from rozert_pay.payment.admin.card_bins import (
    BankAdmin,
    BetmasterNoteAdminMixin,
    BitsoSpeiCardBankAdmin,
    PaymentCardBankAdmin,
)
from rozert_pay.payment.models import Bank, PaymentCardBank
from rozert_pay.payment.systems.bitso_spei.models import BitsoSpeiCardBank
from tests.factories import (
    BankFactory,
    BitsoSpeiCardBankFactory,
    PaymentCardBankFactory,
    UserFactory,
)


@pytest.fixture
def admin_site():
    return AdminSite()


@pytest.fixture
def request_factory():
    return RequestFactory()


@pytest.fixture
def superuser() -> User:
    return UserFactory.create(is_staff=True, is_superuser=True)


@pytest.mark.django_db
class TestBetmasterNoteAdminMixin:
    class MockAdmin(BetmasterNoteAdminMixin, admin.ModelAdmin):  # type: ignore[type-arg]
        pass

    @pytest.fixture
    def test_admin(self, admin_site):
        return self.MockAdmin(Bank, admin_site)

    def _get_request_with_messages(self, request_factory, user):
        request = request_factory.get("/")
        request.user = user
        setattr(request, "session", {})
        messages = FallbackStorage(request)
        setattr(request, "_messages", messages)
        return request

    def test_changelist_view(self, test_admin, request_factory, superuser):
        request = self._get_request_with_messages(request_factory, superuser)
        test_admin.changelist_view(request)
        messages = list(get_messages(request))
        assert len(messages) == 1
        assert str(messages[0]) == test_admin.NOTE_MESSAGE

    def test_add_view(self, test_admin, request_factory, superuser):
        request = self._get_request_with_messages(request_factory, superuser)
        test_admin.add_view(request)
        messages = list(get_messages(request))
        assert len(messages) == 1
        assert str(messages[0]) == test_admin.NOTE_MESSAGE

    def test_change_view(self, test_admin, request_factory, superuser, db):
        bank: Bank = BankFactory.create()
        request = self._get_request_with_messages(request_factory, superuser)
        test_admin.change_view(request, str(bank.id))
        messages = list(get_messages(request))
        assert len(messages) == 1
        assert str(messages[0]) == test_admin.NOTE_MESSAGE


@pytest.mark.django_db
class TestBankAdmin:
    @pytest.fixture
    def bank_admin(self, admin_site):
        return BankAdmin(Bank, admin_site)

    def test_links(self, bank_admin):
        bank: Bank = BankFactory.create()
        links_html = bank_admin.links(bank)
        expected_url = (
            reverse("admin:payment_paymentcardbank_changelist")
            + f"?bank__id__exact={bank.pk}"
        )
        assert expected_url in links_html
        assert "Related BINs" in links_html


@pytest.mark.django_db
class TestPaymentCardBankAdmin:
    @pytest.fixture
    def card_bank_admin(self, admin_site):
        return PaymentCardBankAdmin(PaymentCardBank, admin_site)

    def test_links_no_bitso_banks(self, card_bank_admin):
        card_bank: PaymentCardBank = PaymentCardBankFactory.create()
        links_html = card_bank_admin.links(card_bank)

        bank_url = reverse("admin:payment_bank_change", args=[card_bank.bank_id])
        assert bank_url in links_html
        assert "Bank" in links_html
        assert "Related Bitso SPEI Banks" not in links_html

    def test_links_with_bitso_banks(self, card_bank_admin):
        card_bank: PaymentCardBank = PaymentCardBankFactory.create()
        bitso_bank1: BitsoSpeiCardBank = BitsoSpeiCardBankFactory.create()
        bitso_bank2: BitsoSpeiCardBank = BitsoSpeiCardBankFactory.create()
        getattr(card_bank, "bitso_banks").add(bitso_bank1, bitso_bank2)

        links_html = card_bank_admin.links(card_bank)

        bank_url = reverse("admin:payment_bank_change", args=[card_bank.bank_id])
        assert bank_url in links_html
        assert "Bank" in links_html

        bitso_url = reverse("admin:payment_bitsospeicardbank_changelist")
        assert bitso_url in links_html
        assert f"id__in={bitso_bank1.pk}%2C{bitso_bank2.pk}" in links_html
        assert "Related Bitso SPEI Banks" in links_html


@pytest.mark.django_db
class TestBitsoSpeiCardBankAdmin:
    @pytest.fixture
    def bitso_admin(self, admin_site):
        return BitsoSpeiCardBankAdmin(BitsoSpeiCardBank, admin_site)

    def test_links_no_related_bins(self, bitso_admin):
        bitso_bank: BitsoSpeiCardBank = BitsoSpeiCardBankFactory.create()
        links_html = bitso_admin.links(bitso_bank)
        assert links_html == "-"

    def test_links_with_related_bins(self, bitso_admin):
        bitso_bank: BitsoSpeiCardBank = BitsoSpeiCardBankFactory.create()
        card_bank1: PaymentCardBank = PaymentCardBankFactory.create()
        card_bank2: PaymentCardBank = PaymentCardBankFactory.create()
        bitso_bank.banks.add(card_bank1, card_bank2)

        links_html = bitso_admin.links(bitso_bank)

        bins_url = reverse("admin:payment_paymentcardbank_changelist")
        assert bins_url in links_html
        assert f"id__in={card_bank1.pk}%2C{card_bank2.pk}" in links_html
        assert "Related BINs" in links_html
