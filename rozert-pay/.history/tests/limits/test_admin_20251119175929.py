import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory
from django.urls import reverse
from rozert_pay.limits.admin.customer_limits import (
    BusinessCustomerLimitAdmin,
    CustomerLimitAdmin,
    RiskCustomerLimitAdmin,
)
from rozert_pay.limits.admin.forms import CustomerLimitForm, MerchantLimitForm
from rozert_pay.limits.admin.limit_alert import LimitAlertAdmin
from rozert_pay.limits.admin.merchant_limits import (
    BusinessMerchantLimitAdmin,
    MerchantLimitAdmin,
    RiskMerchantLimitAdmin,
)
from rozert_pay.limits.const import (
    COLOR_OF_ACTIVE_STATUS,
    COLOR_OF_INACTIVE_STATUS,
    CRITICAL_LIMIT_COLOR,
    REGULAR_LIMIT_COLOR,
    LimitPeriod,
)
from rozert_pay.limits.models.common import LimitCategory
from rozert_pay.limits.models.customer_limits import (
    BusinessCustomerLimit,
    CustomerLimit,
    RiskCustomerLimit,
)
from rozert_pay.limits.models.limit_alert import LimitAlert
from rozert_pay.limits.models.merchant_limits import (
    BusinessMerchantLimit,
    LimitType,
    MerchantLimit,
    MerchantLimitScope,
    RiskMerchantLimit,
)
from rozert_pay.payment.admin import MerchantAdmin, WalletAdmin
from rozert_pay.payment.models import Customer, Merchant, Wallet
from tests.factories import (
    CustomerFactory,
    CustomerLimitFactory,
    LimitAlertFactory,
    MerchantFactory,
    MerchantLimitFactory,
    PaymentTransactionFactory,
    UserFactory,
    WalletFactory,
)


@pytest.mark.django_db
@pytest.mark.usefixtures("disable_cache")
class TestCustomerLimitForm:
    def test_clean_duplicate_limit(self):
        customer = CustomerFactory.create()
        CustomerLimitFactory.create(customer=customer, period=LimitPeriod.ONE_HOUR)
        data = {
            "customer": customer.id,
            "period": LimitPeriod.ONE_HOUR,
            "active": True,
            "description": "Test limit",
            "max_successful_operations": 3,
            "max_failed_operations": 2,
            "min_operation_amount": 100,
            "max_operation_amount": 1000,
            "total_successful_amount": 2000,
        }
        form = CustomerLimitForm(data=data)
        assert not form.is_valid()
        assert "__all__" in form.errors
        assert (
            form.errors["__all__"][0]
            == "An active limit for this customer with this period already exists"
        )

    def test_clean_no_duplicate_on_update(self):
        limit = CustomerLimitFactory.create(period=LimitPeriod.ONE_HOUR)
        data = {
            "category": LimitCategory.BUSINESS,
            "customer": limit.customer.id,
            "period": LimitPeriod.ONE_HOUR,
            "active": True,
            "description": "Updated limit",
            "max_successful_operations": 20,
        }
        form = CustomerLimitForm(data=data, instance=limit)
        assert form.is_valid()

    def test_clean_valid_data(self):
        customer = CustomerFactory.create()
        data = {
            "category": LimitCategory.BUSINESS,
            "customer": customer.id,
            "period": LimitPeriod.TWENTY_FOUR_HOURS,
            "active": True,
            "description": "New limit",
            "max_successful_operations": 5,
        }
        form = CustomerLimitForm(data=data)
        assert form.is_valid()


@pytest.mark.django_db
@pytest.mark.usefixtures("disable_cache")
class TestMerchantLimitForm:
    def test_clean_missing_merchant_for_merchant_scope(self):
        data = {
            "category": LimitCategory.BUSINESS,
            "scope": MerchantLimitScope.MERCHANT,
            "limit_type": LimitType.MAX_SUCCESSFUL_DEPOSITS,
            "period": LimitPeriod.ONE_HOUR,
            "active": True,
            "description": "Test limit",
            "max_operations": 10,
        }
        form = MerchantLimitForm(data=data)
        assert not form.is_valid()
        assert "merchant" in form.errors
        assert form.errors["merchant"][0] == "Merchant is required for merchant scope"

    def test_clean_missing_wallet_for_wallet_scope(self):
        data = {
            "category": LimitCategory.BUSINESS,
            "scope": MerchantLimitScope.WALLET,
            "limit_type": LimitType.MAX_SUCCESSFUL_DEPOSITS,
            "period": LimitPeriod.ONE_HOUR,
            "active": True,
            "description": "Test limit",
            "max_operations": 10,
        }
        form = MerchantLimitForm(data=data)
        assert not form.is_valid()
        assert "wallet" in form.errors
        assert form.errors["wallet"][0] == "Wallet is required for wallet scope"

    def test_clean_duplicate_limit_merchant_scope(self):
        merchant = MerchantFactory.create()
        wallet = WalletFactory.create(merchant=merchant)
        MerchantLimitFactory.create(
            merchant=merchant,
            scope=MerchantLimitScope.MERCHANT,
            limit_type=LimitType.MAX_SUCCESSFUL_DEPOSITS,
            period=LimitPeriod.ONE_HOUR,
            wallet=wallet,
        )
        data = {
            "category": LimitCategory.BUSINESS,
            "scope": MerchantLimitScope.MERCHANT,
            "merchant": merchant.id,
            "wallet": wallet.id,
            "limit_type": LimitType.MAX_SUCCESSFUL_DEPOSITS,
            "period": LimitPeriod.ONE_HOUR,
            "active": True,
            "description": "Test limit",
            "max_operations": 10,
        }
        form = MerchantLimitForm(data=data)
        assert not form.is_valid()
        assert "__all__" in form.errors
        assert (
            form.errors["__all__"][0]
            == "An active limit with the same type, period, scope and merchant/wallet already exists"
        )

    def test_clean_duplicate_limit_wallet_scope(self):
        wallet = WalletFactory.create()
        merchant_limit = MerchantLimitFactory.create(
            wallet=wallet,
            scope=MerchantLimitScope.WALLET,
            limit_type=LimitType.MAX_SUCCESSFUL_DEPOSITS,
            period=LimitPeriod.ONE_HOUR,
        )
        data = {
            "category": LimitCategory.BUSINESS,
            "scope": MerchantLimitScope.WALLET,
            "merchant": merchant_limit.merchant,
            "wallet": merchant_limit.wallet,
            "limit_type": LimitType.MAX_SUCCESSFUL_DEPOSITS,
            "period": LimitPeriod.ONE_HOUR,
            "active": True,
            "description": "Test limit",
            "max_operations": 10,
        }
        form = MerchantLimitForm(data=data)
        assert not form.is_valid()
        assert "__all__" in form.errors
        assert (
            form.errors["__all__"][0]
            == "An active limit with the same type, period, scope and merchant/wallet already exists"
        )

    def test_clean_no_duplicate_on_update(self):
        limit = MerchantLimitFactory.create(
            scope=MerchantLimitScope.MERCHANT,
            limit_type=LimitType.MAX_SUCCESSFUL_DEPOSITS,
            period=LimitPeriod.ONE_HOUR,
        )
        data = {
            "category": LimitCategory.BUSINESS,
            "scope": MerchantLimitScope.MERCHANT,
            "merchant": limit.merchant.id if limit.merchant else None,
            "limit_type": LimitType.MAX_SUCCESSFUL_DEPOSITS,
            "period": LimitPeriod.ONE_HOUR,
            "active": True,
            "description": "Updated limit",
            "max_operations": 20,
        }
        form = MerchantLimitForm(data=data, instance=limit)
        assert form.is_valid()

    def test_clean_valid_merchant_scope(self):
        merchant = MerchantFactory.create()
        data = {
            "category": LimitCategory.BUSINESS,
            "scope": MerchantLimitScope.MERCHANT,
            "merchant": merchant.id,
            "limit_type": LimitType.MAX_SUCCESSFUL_DEPOSITS,
            "period": LimitPeriod.TWENTY_FOUR_HOURS,
            "active": True,
            "description": "New limit",
            "max_operations": 5,
        }
        form = MerchantLimitForm(data=data)
        assert form.is_valid()

    def test_clean_valid_wallet_scope(self):
        wallet = WalletFactory.create()
        data = {
            "category": LimitCategory.BUSINESS,
            "scope": MerchantLimitScope.WALLET,
            "wallet": wallet.id,
            "limit_type": LimitType.MAX_SUCCESSFUL_DEPOSITS,
            "period": LimitPeriod.TWENTY_FOUR_HOURS,
            "active": True,
            "description": "New limit",
            "max_operations": 5,
        }
        form = MerchantLimitForm(data=data)
        assert form.is_valid()


@pytest.mark.django_db
@pytest.mark.usefixtures("disable_cache")
class TestCustomerLimitAdmin:
    @pytest.fixture
    def admin(self):
        return CustomerLimitAdmin(model=CustomerLimit, admin_site=AdminSite())

    @pytest.fixture
    def admin_request(self):
        user = UserFactory.create(is_superuser=True)
        request = RequestFactory().get("/")
        request.user = user
        setattr(request, "session", {})
        messages_storage = FallbackStorage(request)
        setattr(request, "_messages", messages_storage)
        return request

    def test_status_colored(self, admin):
        limit = CustomerLimitFactory.create(
            active=True, decline_on_exceed=False, is_critical=False
        )
        colored_status = admin.status_colored(limit)
        assert COLOR_OF_ACTIVE_STATUS in colored_status
        assert "Active" in colored_status

        limit.active = False
        colored_status = admin.status_colored(limit)
        assert COLOR_OF_INACTIVE_STATUS in colored_status
        assert "Inactive" in colored_status

        limit = CustomerLimitFactory.create(
            active=True, decline_on_exceed=True, is_critical=True
        )
        colored_status = admin.status_colored(limit)
        assert COLOR_OF_ACTIVE_STATUS in colored_status
        assert "Active ‼️" in colored_status

    def test_period_display(self, admin):
        limit = CustomerLimitFactory.create(period=LimitPeriod.ONE_HOUR)
        assert admin.period_display(limit) == dict(LimitPeriod.choices).get(
            LimitPeriod.ONE_HOUR
        )

    def test_links(self, admin):
        limit = CustomerLimitFactory.create()
        links = admin.links(limit)
        assert "Audit" in links
        assert reverse("admin:auditlog_logentry_changelist") in links

    def test_invalidate_cache_action(self, admin, admin_request):
        limit = CustomerLimitFactory.create()
        queryset = CustomerLimit.objects.filter(pk=limit.pk)
        admin.invalidate_cache_action(admin_request, queryset)
        messages_list = [m.message for m in admin_request._messages]
        assert "Cache invalidated successfully." in messages_list

    def test_get_fieldsets(self, admin, admin_request):
        fieldsets = admin.get_fieldsets(admin_request)
        assert len(fieldsets) == 2
        assert fieldsets[0][0] == "General"
        assert "active" in fieldsets[0][1]["fields"]
        assert fieldsets[1][0] == "Limit Settings"
        assert "customer" in fieldsets[1][1]["fields"]
        assert "max_successful_operations" in fieldsets[1][1]["fields"]

    def test_get_form(self, admin, admin_request):
        form = admin.get_form(admin_request)()
        assert form.base_fields["customer"].queryset.count() == Customer.objects.count()

    def test_delete_model_with_relations(self, admin, admin_request):
        limit = CustomerLimitFactory.create()
        LimitAlertFactory.create(customer_limit=limit)
        admin.delete_model(admin_request, limit)
        assert not CustomerLimit.objects.filter(pk=limit.pk).exists()
        messages_list = [m.message for m in admin_request._messages]
        assert (
            "Warning: This limit is tied to limit alerts: "
            "1. Deleting it will unbind these relations." in messages_list
        )

    def test_delete_queryset_with_relations(self, admin, admin_request):
        limit1 = CustomerLimitFactory.create()
        CustomerLimitFactory.create()
        LimitAlertFactory.create(customer_limit=limit1)
        queryset = CustomerLimit.objects.all()
        admin.delete_queryset(admin_request, queryset)
        assert not CustomerLimit.objects.exists()
        messages_list = [m.message for m in admin_request._messages]
        assert (
            "Warning: This limit is tied to limit alerts: "
            "1. Deleting it will unbind these relations." in messages_list
        )

    def test_save_model(self, admin, admin_request):
        customer = CustomerFactory.create()
        data = {
            "category": LimitCategory.BUSINESS,
            "customer": customer.id,
            "period": LimitPeriod.ONE_HOUR,
            "active": True,
            "description": "Test limit",
            "max_successful_operations": 10,
        }
        form = CustomerLimitForm(data=data)
        assert form.is_valid()
        limit = form.save(commit=False)
        admin.save_model(admin_request, limit, form, change=False)
        assert CustomerLimit.objects.filter(customer=customer).exists()

    def test_delete_model_with_limit_alert_relations(self, admin, admin_request):
        limit = CustomerLimitFactory.create()
        LimitAlertFactory.create(customer_limit=limit)
        admin.delete_model(admin_request, limit)
        assert not CustomerLimit.objects.filter(pk=limit.pk).exists()
        messages_list = [m.message for m in admin_request._messages]
        assert (
            "Warning: This limit is tied to limit alerts: "
            "1. Deleting it will unbind these relations." in messages_list
        )


@pytest.mark.django_db
@pytest.mark.usefixtures("disable_cache")
class TestRiskCustomerLimitAdmin:
    @pytest.fixture
    def admin(self) -> RiskCustomerLimitAdmin:
        return RiskCustomerLimitAdmin(model=RiskCustomerLimit, admin_site=AdminSite())

    @pytest.fixture
    def admin_request(self):
        user = UserFactory.create(is_superuser=True)
        request = RequestFactory().get("/")
        request.user = user
        setattr(request, "session", {})
        messages_storage = FallbackStorage(request)
        setattr(request, "_messages", messages_storage)
        return request

    def test_has_module_permission(self, admin, admin_request):
        assert admin.has_module_permission(admin_request) is True

    def test_get_form_sets_risk_category_for_new_limit(self, admin, admin_request):
        form = admin.get_form(admin_request, obj=None)()
        assert form.base_fields["category"].initial == LimitCategory.RISK
        assert form.base_fields["category"].disabled is True

    def test_get_form_does_not_modify_existing_limit(self, admin, admin_request):
        limit = CustomerLimitFactory.create(category=LimitCategory.RISK)
        form = admin.get_form(admin_request, obj=limit)()
        assert "category" in form.base_fields

    def test_get_readonly_fields_excludes_category_for_new_limit(self, admin, admin_request):
        readonly_fields = admin.get_readonly_fields(admin_request, obj=None)
        assert "category" not in readonly_fields

    def test_get_readonly_fields_includes_category_for_existing_limit(self, admin, admin_request):
        limit = CustomerLimitFactory.create(category=LimitCategory.RISK)
        readonly_fields = admin.get_readonly_fields(admin_request, obj=limit)
        assert "category" in readonly_fields

    def test_save_model_sets_risk_category(self, admin, admin_request):
        customer = CustomerFactory.create()
        data = {

            "customer": customer.id,
            "period": LimitPeriod.ONE_HOUR,
            "active": True,
            "description": "Test risk limit",
            "max_successful_operations": 10,
        }
        form = CustomerLimitForm(data=data)
        assert form.is_valid()
        limit = form.save(commit=False)
        admin.save_model(admin_request, limit, form, change=False)
        assert limit.category == LimitCategory.RISK

    def test_queryset_filters_by_risk_category(self, admin):
        CustomerLimitFactory.create(category=LimitCategory.RISK)
        CustomerLimitFactory.create(category=LimitCategory.BUSINESS)
        assert RiskCustomerLimit.objects.count() == 1


@pytest.mark.django_db
@pytest.mark.usefixtures("disable_cache")
class TestBusinessCustomerLimitAdmin:
    @pytest.fixture
    def admin(self) -> BusinessCustomerLimitAdmin:
        return BusinessCustomerLimitAdmin(model=BusinessCustomerLimit, admin_site=AdminSite())

    @pytest.fixture
    def admin_request(self):
        user = UserFactory.create(is_superuser=True)
        request = RequestFactory().get("/")
        request.user = user
        setattr(request, "session", {})
        messages_storage = FallbackStorage(request)
        setattr(request, "_messages", messages_storage)
        return request

    def test_has_module_permission(self, admin, admin_request):
        assert admin.has_module_permission(admin_request) is True

    def test_get_form_sets_business_category_for_new_limit(self, admin, admin_request):
        form = admin.get_form(admin_request, obj=None)()
        assert form.base_fields["category"].initial == LimitCategory.BUSINESS
        assert form.base_fields["category"].disabled is True

    def test_get_form_does_not_modify_existing_limit(self, admin, admin_request):
        limit = CustomerLimitFactory.create(category=LimitCategory.BUSINESS)
        form = admin.get_form(admin_request, obj=limit)()
        assert "category" in form.base_fields

    def test_get_readonly_fields_excludes_category_for_new_limit(self, admin, admin_request):
        readonly_fields = admin.get_readonly_fields(admin_request, obj=None)
        assert "category" not in readonly_fields

    def test_get_readonly_fields_includes_category_for_existing_limit(self, admin, admin_request):
        limit = CustomerLimitFactory.create(category=LimitCategory.BUSINESS)
        readonly_fields = admin.get_readonly_fields(admin_request, obj=limit)
        assert "category" in readonly_fields

    def test_save_model_sets_business_category(self, admin, admin_request):
        customer = CustomerFactory.create()
        data = {
            "customer": customer.id,
            "period": LimitPeriod.ONE_HOUR,
            "active": True,
            "description": "Test business limit",
            "max_successful_operations": 10,
        }
        form = CustomerLimitForm(data=data)
        assert form.is_valid()
        limit = form.save(commit=False)
        admin.save_model(admin_request, limit, form, change=False)
        assert limit.category == LimitCategory.BUSINESS

    def test_queryset_filters_by_business_category(self, admin):
        CustomerLimitFactory.create(category=LimitCategory.RISK)
        CustomerLimitFactory.create(category=LimitCategory.BUSINESS)
        assert BusinessCustomerLimit.objects.count() == 1


@pytest.mark.django_db
@pytest.mark.usefixtures("disable_cache")
class TestMerchantLimitAdmin:
    @pytest.fixture
    def admin(self):
        return MerchantLimitAdmin(model=MerchantLimit, admin_site=AdminSite())

    @pytest.fixture
    def admin_request(self):
        user = UserFactory.create(is_superuser=True)
        request = RequestFactory().get("/")
        request.user = user
        setattr(request, "session", {})
        messages_storage = FallbackStorage(request)
        setattr(request, "_messages", messages_storage)
        return request

    @pytest.fixture
    def request_non_superuser(self):
        user = UserFactory.create(is_superuser=False)
        request = RequestFactory().get("/")
        request.user = user
        setattr(request, "session", {})
        messages_storage = FallbackStorage(request)
        setattr(request, "_messages", messages_storage)
        return request

    def test_status_colored(self, admin):
        limit = MerchantLimitFactory.create(
            active=True, decline_on_exceed=False, is_critical=False
        )
        colored_status = admin.status_colored(limit)
        assert COLOR_OF_ACTIVE_STATUS in colored_status
        assert "Active" in colored_status

        limit.active = False
        colored_status = admin.status_colored(limit)
        assert COLOR_OF_INACTIVE_STATUS in colored_status
        assert "Inactive" in colored_status

        limit = MerchantLimitFactory.create(
            active=True, decline_on_exceed=True, is_critical=True
        )
        colored_status = admin.status_colored(limit)
        assert COLOR_OF_ACTIVE_STATUS in colored_status
        assert "Active ‼️" in colored_status

    def test_period_display(self, admin):
        limit = MerchantLimitFactory.create(period=LimitPeriod.ONE_HOUR)
        assert admin.period_display(limit) == dict(LimitPeriod.choices).get(
            LimitPeriod.ONE_HOUR
        )

    def test_scope_name(self, admin):
        limit = MerchantLimitFactory.create(scope=MerchantLimitScope.MERCHANT)
        assert admin.scope_name(limit) == dict(MerchantLimitScope.choices).get(
            MerchantLimitScope.MERCHANT
        )
        limit.scope = MerchantLimitScope.WALLET
        assert admin.scope_name(limit) == dict(MerchantLimitScope.choices).get(
            MerchantLimitScope.WALLET
        )

    def test_merchant_name(self, admin):
        limit = MerchantLimitFactory.create(
            merchant=MerchantFactory.create(name="Test Merchant")
        )
        assert admin.merchant_name(limit) == "Test Merchant"
        limit.merchant = None
        assert admin.merchant_name(limit) == "-"

    def test_wallet_display(self, admin):
        limit = MerchantLimitFactory.create(
            wallet=WalletFactory.create(name="Test Wallet")
        )
        assert admin.wallet_display(limit) == "Test Wallet"
        limit.wallet = None
        assert admin.wallet_display(limit) == "-"

    def test_limit_type_display(self, admin):
        limit = MerchantLimitFactory.create(
            limit_type=LimitType.MAX_SUCCESSFUL_DEPOSITS
        )
        assert admin.limit_type_display(limit) == dict(LimitType.choices).get(
            LimitType.MAX_SUCCESSFUL_DEPOSITS
        )

    def test_links(self, admin):
        limit = MerchantLimitFactory.create()
        links = admin.links(limit)
        assert "Audit" in links
        assert reverse("admin:auditlog_logentry_changelist") in links

    def test_links_wallet_scope(self, admin):
        wallet = WalletFactory.create()
        limit = MerchantLimitFactory.create(
            scope=MerchantLimitScope.WALLET, wallet=wallet
        )
        links = admin.links(limit)
        assert (
            reverse("admin:payment_paymenttransaction_changelist")
            + f"?limit_trigger_logs__merchant_limit__id__exact={limit.pk}"
        ) in links
        assert "Transactions" in links

    def test_invalidate_cache_action(self, admin, admin_request):
        limit = MerchantLimitFactory.create()
        queryset = MerchantLimit.objects.filter(pk=limit.pk)
        admin.invalidate_cache_action(admin_request, queryset)
        messages_list = [m.message for m in admin_request._messages]
        assert "Cache invalidated successfully." in messages_list

    def test_get_fieldsets(self, admin, admin_request):
        fieldsets = admin.get_fieldsets(admin_request)
        assert len(fieldsets) == 2
        assert fieldsets[0] == (
            "General",
            {
                "fields": [
                    "active",
                    "category",
                    "description",
                    "decline_on_exceed",
                    "is_critical",
                    "notification_groups",
                    "slack_channel_override",
                ]
            },
        )
        assert fieldsets[1] == (
            "Limit Settings",
            {
                "fields": [
                    "scope",
                    "merchant",
                    "wallet",
                    "limit_type",
                    "period",
                    "max_operations",
                    "max_overall_decline_percent",
                    "max_withdrawal_decline_percent",
                    "max_deposit_decline_percent",
                    "min_amount",
                    "max_amount",
                    "total_amount",
                    "max_ratio",
                    "burst_minutes",
                ]
            },
        )

    def test_get_form(self, admin, admin_request):
        form = admin.get_form(admin_request)()
        assert form.base_fields["merchant"].queryset.count() == Merchant.objects.count()
        assert form.base_fields["wallet"].queryset.count() == Wallet.objects.count()

    def test_get_list_display_superuser(self, admin, admin_request):
        list_display = admin.get_list_display(admin_request)
        assert "is_critical" in list_display

    def test_get_list_display_non_superuser(self, admin, request_non_superuser):
        list_display = admin.get_list_display(request_non_superuser)
        assert "is_critical" not in list_display

    def test_delete_model_with_relations(self, admin, admin_request):
        limit = MerchantLimitFactory.create()
        LimitAlertFactory.create(merchant_limit=limit)
        admin.delete_model(admin_request, limit)
        assert not MerchantLimit.objects.filter(pk=limit.pk).exists()
        messages_list = [m.message for m in admin_request._messages]
        assert (
            "Warning: This limit is tied to limit alerts: "
            "1. Deleting it will unbind these relations." in messages_list
        )

    def test_delete_queryset_with_relations(self, admin, admin_request):
        limit1 = MerchantLimitFactory.create()
        MerchantLimitFactory.create()
        LimitAlertFactory.create(merchant_limit=limit1)
        queryset = MerchantLimit.objects.all()
        admin.delete_queryset(admin_request, queryset)
        assert not MerchantLimit.objects.exists()
        messages_list = [m.message for m in admin_request._messages]
        assert (
            "Warning: This limit is tied to limit alerts: "
            "1. Deleting it will unbind these relations." in messages_list
        )

    def test_save_model(self, admin, admin_request):
        merchant = MerchantFactory.create()
        data = {
            "category": LimitCategory.BUSINESS,
            "scope": MerchantLimitScope.MERCHANT,
            "merchant": merchant.id,
            "limit_type": LimitType.MAX_SUCCESSFUL_DEPOSITS,
            "period": LimitPeriod.ONE_HOUR,
            "active": True,
            "description": "Test limit",
            "max_operations": 10,
        }
        form = MerchantLimitForm(data=data)
        assert form.is_valid()
        limit = form.save(commit=False)
        admin.save_model(admin_request, limit, form, change=False)
        assert MerchantLimit.objects.filter(merchant=merchant).exists()

    def test_delete_model_with_limit_alert_relations(self, admin, admin_request):
        limit = MerchantLimitFactory.create()
        LimitAlertFactory.create(merchant_limit=limit)
        admin.delete_model(admin_request, limit)
        assert not MerchantLimit.objects.filter(pk=limit.pk).exists()
        messages_list = [m.message for m in admin_request._messages]
        assert (
            "Warning: This limit is tied to limit alerts: "
            "1. Deleting it will unbind these relations." in messages_list
        )


@pytest.mark.django_db
@pytest.mark.usefixtures("disable_cache")
class TestRiskMerchantLimitAdmin:
    @pytest.fixture
    def admin(self) -> RiskMerchantLimitAdmin:
        return RiskMerchantLimitAdmin(model=RiskMerchantLimit, admin_site=AdminSite())

    @pytest.fixture
    def admin_request(self):
        user = UserFactory.create(is_superuser=True)
        request = RequestFactory().get("/")
        request.user = user
        setattr(request, "session", {})
        messages_storage = FallbackStorage(request)
        setattr(request, "_messages", messages_storage)
        return request

    def test_has_module_permission(self, admin, admin_request):
        assert admin.has_module_permission(admin_request) is True

    def test_get_form_sets_risk_category_for_new_limit(self, admin, admin_request):
        form = admin.get_form(admin_request, obj=None)()
        assert form.base_fields["category"].initial == LimitCategory.RISK
        assert form.base_fields["category"].disabled is True

    def test_get_form_does_not_modify_existing_limit(self, admin, admin_request):
        limit = MerchantLimitFactory.create(category=LimitCategory.RISK)
        form = admin.get_form(admin_request, obj=limit)()
        assert "category" in form.base_fields

    def test_get_readonly_fields_excludes_category_for_new_limit(self, admin, admin_request):
        readonly_fields = admin.get_readonly_fields(admin_request, obj=None)
        assert "category" not in readonly_fields

    def test_get_readonly_fields_includes_category_for_existing_limit(self, admin, admin_request):
        limit = MerchantLimitFactory.create(category=LimitCategory.RISK)
        readonly_fields = admin.get_readonly_fields(admin_request, obj=limit)
        assert "category" in readonly_fields

    def test_save_model_sets_risk_category(self, admin, admin_request):
        merchant = MerchantFactory.create()
        data = {
            "scope": MerchantLimitScope.MERCHANT,
            "merchant": merchant.id,
            "limit_type": LimitType.MAX_SUCCESSFUL_DEPOSITS,
            "period": LimitPeriod.ONE_HOUR,
            "active": True,
            "description": "Test risk limit",
            "max_operations": 10,
        }
        form = MerchantLimitForm(data=data)
        assert form.is_valid()
        limit = form.save(commit=False)
        admin.save_model(admin_request, limit, form, change=False)
        assert limit.category == LimitCategory.RISK

    def test_queryset_filters_by_risk_category(self, admin):
        MerchantLimitFactory.create(category=LimitCategory.RISK)
        MerchantLimitFactory.create(category=LimitCategory.BUSINESS)
        assert RiskMerchantLimit.objects.count() == 1


@pytest.mark.django_db
@pytest.mark.usefixtures("disable_cache")
class TestBusinessMerchantLimitAdmin:
    @pytest.fixture
    def admin(self) -> BusinessMerchantLimitAdmin:
        return BusinessMerchantLimitAdmin(model=BusinessMerchantLimit, admin_site=AdminSite())

    @pytest.fixture
    def admin_request(self):
        user = UserFactory.create(is_superuser=True)
        request = RequestFactory().get("/")
        request.user = user
        setattr(request, "session", {})
        messages_storage = FallbackStorage(request)
        setattr(request, "_messages", messages_storage)
        return request

    def test_has_module_permission(self, admin, admin_request):
        assert admin.has_module_permission(admin_request) is True

    def test_get_form_sets_business_category_for_new_limit(self, admin, admin_request):
        form = admin.get_form(admin_request, obj=None)()
        assert form.base_fields["category"].initial == LimitCategory.BUSINESS
        assert form.base_fields["category"].disabled is True

    def test_get_form_does_not_modify_existing_limit(self, admin, admin_request):
        limit = MerchantLimitFactory.create(category=LimitCategory.BUSINESS)
        form = admin.get_form(admin_request, obj=limit)()
        assert "category" in form.base_fields

    def test_get_readonly_fields_excludes_category_for_new_limit(self, admin, admin_request):
        readonly_fields = admin.get_readonly_fields(admin_request, obj=None)
        assert "category" not in readonly_fields

    def test_get_readonly_fields_includes_category_for_existing_limit(self, admin, admin_request):
        limit = MerchantLimitFactory.create(category=LimitCategory.BUSINESS)
        readonly_fields = admin.get_readonly_fields(admin_request, obj=limit)
        assert "category" in readonly_fields

    def test_save_model_sets_business_category(self, admin, admin_request):
        merchant = MerchantFactory.create()
        data = {
            "scope": MerchantLimitScope.MERCHANT,
            "merchant": merchant.id,
            "limit_type": LimitType.MAX_SUCCESSFUL_DEPOSITS,
            "period": LimitPeriod.ONE_HOUR,
            "active": True,
            "description": "Test business limit",
            "max_operations": 10,
        }
        form = MerchantLimitForm(data=data)
        assert form.is_valid()
        limit = form.save(commit=False)
        admin.save_model(admin_request, limit, form, change=False)
        assert limit.category == LimitCategory.BUSINESS

    def test_queryset_filters_by_business_category(self, admin):
        MerchantLimitFactory.create(category=LimitCategory.RISK)
        MerchantLimitFactory.create(category=LimitCategory.BUSINESS)
        assert BusinessMerchantLimit.objects.count() == 1


@pytest.mark.django_db
@pytest.mark.usefixtures("disable_cache")
class TestLimitAlertAdmin:
    @pytest.fixture
    def admin(self):
        return LimitAlertAdmin(model=LimitAlert, admin_site=AdminSite())

    @pytest.fixture
    def admin_request(self):
        user = UserFactory.create(is_superuser=True)
        request = RequestFactory().get("/")
        request.user = user
        setattr(request, "session", {})
        messages_storage = FallbackStorage(request)
        setattr(request, "_messages", messages_storage)
        return request

    def test_limit_type_colored_regular_customer(self, admin):
        customer_limit = CustomerLimitFactory.create(is_critical=False)
        limit_alert = LimitAlertFactory.create(
            customer_limit=customer_limit, merchant_limit=None
        )
        colored_type = admin.limit_type_colored(limit_alert)

        assert REGULAR_LIMIT_COLOR in colored_type
        assert "Customer Limit" in colored_type

    def test_limit_type_colored_critical_customer(self, admin):
        customer_limit = CustomerLimitFactory.create(is_critical=True)
        limit_alert = LimitAlertFactory.create(
            customer_limit=customer_limit, merchant_limit=None
        )

        colored_type = admin.limit_type_colored(limit_alert)

        assert CRITICAL_LIMIT_COLOR in colored_type
        assert "Customer Limit" in colored_type

    def test_limit_type_colored_regular_merchant(self, admin):
        merchant_limit = MerchantLimitFactory.create(is_critical=False)
        limit_alert = LimitAlertFactory.create(
            merchant_limit=merchant_limit, customer_limit=None
        )

        colored_type = admin.limit_type_colored(limit_alert)

        assert REGULAR_LIMIT_COLOR in colored_type
        assert "Merchant Limit" in colored_type

    def test_limit_type_colored_critical_merchant(self, admin):
        merchant_limit = MerchantLimitFactory.create(is_critical=True)
        limit_alert = LimitAlertFactory.create(
            merchant_limit=merchant_limit, customer_limit=None
        )

        colored_type = admin.limit_type_colored(limit_alert)

        assert CRITICAL_LIMIT_COLOR in colored_type
        assert "Merchant Limit" in colored_type

    def test_transaction_display(self, admin):
        transaction = PaymentTransactionFactory.create(
            type="DEPOSIT", amount=100, currency="USD"
        )
        limit_alert = LimitAlertFactory.create(transaction=transaction)
        assert (
            admin.transaction_display(limit_alert)
            == f"DEPOSIT #{transaction.id} (100 USD)"
        )

    def test_customer_limit_display(self, admin):
        customer_limit = CustomerLimitFactory.create(description="Test Customer Limit")
        limit_alert = LimitAlertFactory.create(
            customer_limit=customer_limit, merchant_limit=None
        )
        assert admin.customer_limit_display(limit_alert) == "Test Customer Limit"

        limit_alert = LimitAlertFactory.create(customer_limit=None)
        assert admin.customer_limit_display(limit_alert) == "-"

    def test_merchant_limit_display(self, admin):
        merchant_limit = MerchantLimitFactory.create(description="Test Merchant Limit")
        limit_alert = LimitAlertFactory.create(
            merchant_limit=merchant_limit, customer_limit=None
        )
        assert admin.merchant_limit_display(limit_alert) == "Test Merchant Limit"

        limit_alert = LimitAlertFactory.create(merchant_limit=None)
        assert admin.merchant_limit_display(limit_alert) == "-"

    def test_notification_text_display(self, admin):
        limit_alert = LimitAlertFactory.create(notification_text="Test Notification")
        assert admin.notification_text_display(limit_alert) == "Test Notification"

        limit_alert = LimitAlertFactory.create(notification_text=None)
        assert admin.notification_text_display(limit_alert) == "-"

        limit_alert = LimitAlertFactory.create(notification_text="")
        assert admin.notification_text_display(limit_alert) == "-"

    def test_extra_data(self, admin):
        limit_alert = LimitAlertFactory.create(extra={"key": "value"})
        assert admin.extra_data(limit_alert) == "{'key': 'value'}"

    def test_links(self, admin):
        transaction = PaymentTransactionFactory.create()
        customer_limit = CustomerLimitFactory.create()
        merchant_limit = MerchantLimitFactory.create()
        limit_alert_customer = LimitAlertFactory.create(
            transaction=transaction,
            customer_limit=customer_limit,
            merchant_limit=None,
        )
        limit_alert_merchant = LimitAlertFactory.create(
            transaction=transaction,
            customer_limit=None,
            merchant_limit=merchant_limit,
        )
        links_customer = admin.links(limit_alert_customer)
        links_merchant = admin.links(limit_alert_merchant)

        assert (
            reverse("admin:payment_paymenttransaction_change", args=[transaction.pk])
            in links_customer
        )
        assert (
            reverse("admin:limits_customerlimit_change", args=[customer_limit.pk])
            in links_customer
        )
        assert (
            reverse("admin:limits_merchantlimit_change", args=[merchant_limit.pk])
            not in links_customer
        )

        assert (
            reverse("admin:limits_merchantlimit_change", args=[merchant_limit.pk])
            in links_merchant
        )
        assert reverse("admin:auditlog_logentry_changelist") in links_customer
        assert reverse("admin:auditlog_logentry_changelist") in links_merchant

    def test_get_fieldsets(self, admin, admin_request):
        fieldsets = admin.get_fieldsets(admin_request)
        assert len(fieldsets) == 1
        assert fieldsets[0][0] == "General"
        assert "customer_limit" in fieldsets[0][1]["fields"]
        assert "merchant_limit" in fieldsets[0][1]["fields"]
        assert "transaction" in fieldsets[0][1]["fields"]
        assert "extra" in fieldsets[0][1]["fields"]

    def test_get_list_display(self, admin, admin_request):
        list_display = admin.get_list_display(admin_request)
        assert "limit_type_colored" in list_display
        assert "transaction_display" in list_display
        assert "customer_limit_display" in list_display
        assert "merchant_limit_display" in list_display
        assert "created_at" in list_display
        assert "extra_data" in list_display
        assert "links" in list_display

    def test_get_list_filter(self, admin, admin_request):
        list_filter = admin.get_list_filter(admin_request)
        assert "customer_limit" in list_filter
        assert "merchant_limit" in list_filter
        assert "created_at" in list_filter

    def test_get_search_fields(self, admin, admin_request):
        search_fields = admin.get_search_fields(admin_request)
        assert "transaction__uuid" in search_fields
        assert "customer_limit__description" in search_fields
        assert "merchant_limit__description" in search_fields

    def test_get_readonly_fields(self, admin, admin_request):
        readonly_fields = admin.get_readonly_fields(admin_request)
        assert "links" in readonly_fields


@pytest.mark.django_db
@pytest.mark.usefixtures("disable_cache")
class TestMerchantAdmin:
    @pytest.fixture
    def admin(self):
        return MerchantAdmin(model=Merchant, admin_site=AdminSite())

    @pytest.fixture
    def admin_request(self):
        user = UserFactory.create(is_superuser=True)
        request = RequestFactory().get("/")
        request.user = user
        setattr(request, "session", {})
        messages_storage = FallbackStorage(request)
        setattr(request, "_messages", messages_storage)
        return request

    def test_links(self, admin):
        merchant = MerchantFactory.create()
        links_html = admin.links(merchant)

        merchant_limits_url = (
            reverse("admin:limits_merchantlimit_changelist")
            + f"?merchant__id__exact={merchant.pk}"
        )
        wallets_url = (
            reverse("admin:payment_wallet_changelist")
            + f"?merchant__id__exact={merchant.pk}"
        )

        assert merchant_limits_url in links_html
        assert wallets_url in links_html
        assert "Merchant Limits" in links_html
        assert "Wallets" in links_html

        assert links_html.startswith("<ul>")
        assert links_html.endswith("</ul>")
        assert links_html.count("<li>") == 2
        assert links_html.count("<a href=") == 2


@pytest.mark.django_db
@pytest.mark.usefixtures("disable_cache")
class TestWalletAdmin:
    @pytest.fixture
    def admin(self):
        return WalletAdmin(model=Wallet, admin_site=AdminSite())

    @pytest.fixture
    def admin_request(self):
        user = UserFactory.create(is_superuser=True)
        request = RequestFactory().get("/")
        request.user = user
        setattr(request, "session", {})
        return request

    def test_links(self, admin, settings):
        wallet = WalletFactory.create()
        links_html = admin.links(wallet)

        expected_links = [
            (
                reverse("admin:limits_merchantlimit_changelist")
                + f"?wallet__id__exact={wallet.pk}",
                "Wallet Limits",
            ),
            (
                reverse("admin:payment_paymenttransaction_changelist")
                + f"?wallet__wallet__id__exact={wallet.pk}",
                "Transactions",
            ),
            (
                f"{settings.BETMASTER_BASE_URL}admin/payment/dbcustomcredentialrule/"
                f"?rozert_wallet_id={wallet.uuid}",
                "Betmaster creds",
            ),
        ]

        for url, text in expected_links:
            assert url in links_html
            assert text in links_html

        assert links_html.startswith("<ul>")
        assert links_html.endswith("</ul>")
        assert links_html.count("<li>") == 3
        assert links_html.count("<a href=") == 3
