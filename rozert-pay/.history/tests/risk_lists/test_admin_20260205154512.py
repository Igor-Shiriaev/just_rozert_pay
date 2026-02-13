import urllib.parse

import pytest
from django.contrib.admin.sites import AdminSite
from django.http import HttpRequest
from django.test import RequestFactory
from django.urls import reverse
from rozert_pay.account.models import User
from rozert_pay.risk_lists.admin import (
    BlackListEntryAdmin,
    MerchantBlackListEntryAdmin,
    WhiteListEntryAdmin,
)
from rozert_pay.risk_lists.const import ListType, Scope, ValidFor
from rozert_pay.risk_lists.models import (
    BlackListEntry,
    MerchantBlackListEntry,
    WhiteListEntry,
)
from tests.factories import MerchantFactory, UserFactory
from tests.risk_lists.factories import BlackListEntryFactory, WhiteListEntryFactory


@pytest.fixture
def admin_user() -> User:
    return UserFactory.create(is_staff=True, is_superuser=True)


@pytest.fixture
def admin_request(admin_user: User) -> HttpRequest:
    request = RequestFactory().get("/")
    request.user = admin_user
    return request


@pytest.mark.django_db
class TestWhiteListEntryAdmin:
    @pytest.fixture
    def admin(self) -> WhiteListEntryAdmin:
        return WhiteListEntryAdmin(WhiteListEntry, AdminSite())

    def test_form_initials(
        self, admin: WhiteListEntryAdmin, admin_request: HttpRequest
    ) -> None:
        form_class = admin.get_form(admin_request)
        form = form_class()
        assert form.fields["list_type"].initial == ListType.WHITE
        assert form.fields["valid_for"].initial == ValidFor.H24

    def test_save_model_logic(
        self, admin: WhiteListEntryAdmin, admin_request: HttpRequest
    ) -> None:
        obj = WhiteListEntryFactory.create(
            email="a@x.com",
            phone="",
            ip=None,  # phone and ip are empty
        )
        form_mock = type(
            "FormMock",
            (),
            {"cleaned_data": {"match_fields": ["email", "phone", "ip"]}},
        )()

        admin.save_model(admin_request, obj, form_mock, change=False)

        assert obj.added_by == admin_request.user
        assert obj.match_fields == ["email"]

    def test_get_queryset_filters_by_list_type(
        self, admin: WhiteListEntryAdmin, admin_request: HttpRequest
    ) -> None:
        WhiteListEntryFactory.create()
        BlackListEntryFactory.create()  # noise

        qs = admin.get_queryset(admin_request)
        assert qs.count() == 1
        assert qs.first().list_type == ListType.WHITE

    def test_clone_view_redirects_with_prefilled_data(
        self, admin: WhiteListEntryAdmin, admin_request: HttpRequest
    ) -> None:
        merchant = MerchantFactory.create()
        entry = WhiteListEntryFactory.create(
            email="a@x.com", reason="copy me", merchant=merchant
        )
        response = admin.clone_view(admin_request, entry.pk)

        assert response.status_code == 302
        params = urllib.parse.parse_qs(urllib.parse.urlparse(response.url).query)

        assert params.get("is_deleted") == ["False"]
        assert params.get("list_type") == [ListType.WHITE.value]
        assert params.get("scope") == [Scope.MERCHANT.value]
        assert params.get("merchant") == [str(merchant.pk)]
        assert params.get("reason") == ["copy me"]
        assert "created_at" not in params

    def test_changelist_redirects_to_show_active(
        self, admin: WhiteListEntryAdmin, admin_user: User
    ) -> None:
        req = RequestFactory().get(
            reverse("admin:risk_lists_whitelistentry_changelist")
        )
        req.user = admin_user
        resp = admin.changelist_view(req)
        assert resp.status_code == 302
        assert "is_deleted__exact=0" in resp.url

    def test_disallow_change_for_deleted_entry(
        self, admin: WhiteListEntryAdmin, admin_request: HttpRequest
    ) -> None:
        entry = WhiteListEntryFactory.create(is_deleted=True)
        assert admin.has_change_permission(admin_request, entry) is False


@pytest.mark.django_db
class TestBlackListEntryAdmin:
    @pytest.fixture
    def admin(self) -> BlackListEntryAdmin:
        return BlackListEntryAdmin(BlackListEntry, AdminSite())

    def test_form_hides_fields(
        self, admin: BlackListEntryAdmin, admin_request: HttpRequest
    ) -> None:
        form_class = admin.get_form(admin_request)
        form = form_class()
        assert form.fields["list_type"].initial == ListType.BLACK
        assert form.fields["valid_for"].initial == "PERMANENT"
        assert "HiddenInput" in str(form.fields["valid_for"].widget)


@pytest.mark.django_db
class TestMerchantBlackListEntryAdmin:
    @pytest.fixture
    def admin(self) -> MerchantBlackListEntryAdmin:
        return MerchantBlackListEntryAdmin(MerchantBlackListEntry, AdminSite())

    def test_form_hides_fields(
        self, admin: MerchantBlackListEntryAdmin, admin_request: HttpRequest
    ) -> None:
        form_class = admin.get_form(admin_request)
        form = form_class()
        assert form.fields["list_type"].initial == ListType.MERCHANT_BLACK
        assert form.fields["valid_for"].initial == "PERMANENT"
        assert "HiddenInput" in str(form.fields["valid_for"].widget)
        assert form.fields["scope"].initial == Scope.MERCHANT
        assert "HiddenInput" in str(form.fields["scope"].widget)
