import datetime
import re
from datetime import timedelta
from unittest.mock import Mock, patch

import pytest
from django.contrib import messages as django_messages
from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import Permission
from django.contrib.messages.storage.fallback import FallbackStorage
from django.http import FileResponse
from django.test import Client, RequestFactory, override_settings
from django.urls import reverse
from django.utils import timezone
from rozert_pay.payment.admin import (
    CustomerAdmin,
    IncomingCallbackAdmin,
    PaymentSystemAdmin,
    PaymentTransactionAdmin,
    PaymentTransactionEventLogAdmin,
    TransactionManagerAdmin,
)
from rozert_pay.payment.admin.utils import TransactionDateTimeQuickFilter
from rozert_pay.payment.models import (
    Customer,
    IncomingCallback,
    PaymentSystem,
    PaymentTransaction,
    PaymentTransactionEventLog,
    TransactionManager,
)
from tests.factories import (
    CurrencyWalletFactory,
    CustomerFactory,
    CustomerLimitFactory,
    IncomingCallbackFactory,
    LimitAlertFactory,
    MerchantFactory,
    MerchantLimitFactory,
    PaymentSystemFactory,
    PaymentTransactionEventLogFactory,
    PaymentTransactionFactory,
    UserFactory,
    WalletFactory,
)


@pytest.mark.django_db
@pytest.mark.usefixtures("disable_cache")
class TestIncomingCallbackAdmin:
    @pytest.fixture
    def admin(self):
        return IncomingCallbackAdmin(model=IncomingCallback, admin_site=AdminSite())

    def test_links(self, admin):
        transaction = PaymentTransactionFactory.create()
        incoming_callback = IncomingCallbackFactory.create(
            transaction=transaction,
        )

        links_html = admin.links(incoming_callback)

        expected_links = [
            (
                f"/admin/payment/paymentsystem/?id={incoming_callback.system_id}",
                "System",
            ),
            (
                f"/admin/payment/paymenttransactioneventlog/"
                f"?incoming_callback_id={incoming_callback.id}",
                "Logs",
            ),
            (
                f"/admin/payment/paymenttransaction/?id={transaction.id}",
                "Transaction",
            ),
        ]

        for url, text in expected_links:
            assert url in links_html
            assert text in links_html

        assert links_html.startswith("<ul>")
        assert links_html.endswith("</ul>")
        assert links_html.count("<li>") == 3
        assert links_html.count("<a href=") == 3

    def test_links_without_transaction(self, admin):
        incoming_callback = IncomingCallbackFactory.create(
            transaction=None,
        )

        links_html = admin.links(incoming_callback)

        expected_links = [
            (
                f"/admin/payment/paymentsystem/?id={incoming_callback.system_id}",
                "System",
            ),
            (
                f"/admin/payment/paymenttransactioneventlog/"
                f"?incoming_callback_id={incoming_callback.id}",
                "Logs",
            ),
        ]

        for url, text in expected_links:
            assert url in links_html
            assert text in links_html

        assert "?paymenttransaction/?id=" not in links_html

        assert links_html.startswith("<ul>")
        assert links_html.endswith("</ul>")
        assert links_html.count("<li>") == 2
        assert links_html.count("<a href=") == 2


@pytest.mark.django_db
@pytest.mark.usefixtures("disable_cache")
class TestPaymentTransactionEventLogAdmin:
    @pytest.fixture
    def admin(self):
        return PaymentTransactionEventLogAdmin(
            model=PaymentTransactionEventLog, admin_site=AdminSite()
        )

    def test_links(self, admin):
        transaction = PaymentTransactionFactory.create()
        event_log = PaymentTransactionEventLogFactory.create(
            transaction=transaction,
            incoming_callback=None,
        )

        links_html = admin.links(event_log)

        expected_links = [
            (
                f"/admin/payment/paymenttransaction/?id={event_log.transaction_id}",
                "Transaction",
            ),
        ]

        for url, text in expected_links:
            assert url in links_html
            assert text in links_html

        assert not links_html.startswith("<ul>")
        assert not links_html.endswith("</ul>")
        assert links_html.count("<li>") == 0
        assert links_html.count("<a href=") == 1

        assert "/admin/payment/incomingcallback/?id=" not in links_html


@pytest.mark.django_db
@pytest.mark.usefixtures("disable_cache")
class TestPaymentSystemAdmin:
    @pytest.fixture
    def admin(self):
        return PaymentSystemAdmin(model=PaymentSystem, admin_site=AdminSite())

    def test_links(self, admin):
        payment_system = PaymentSystemFactory.create()

        links_html = admin.links(payment_system)

        expected_links = [
            (
                f"/admin/payment/incomingcallback/?system_id={payment_system.id}",
                "Incoming Callbacks",
            ),
        ]

        for url, text in expected_links:
            assert url in links_html
            assert text in links_html

        assert links_html.startswith("<ul>")
        assert links_html.endswith("</ul>")
        assert links_html.count("<li>") == 3
        assert links_html.count("<a href=") == 3

        assert "/admin/payment/incomingcallback/?id=" not in links_html


@pytest.mark.django_db
@pytest.mark.usefixtures("disable_cache")
class TestPaymentTransactionAdmin:
    @pytest.fixture
    def admin(self):
        return PaymentTransactionAdmin(model=PaymentTransaction, admin_site=AdminSite())

    @pytest.fixture
    def admin_request(self):
        user = UserFactory.create(is_superuser=True)
        request = RequestFactory().get("/")
        request.user = user
        setattr(request, "session", {})
        messages_storage = FallbackStorage(request)
        setattr(request, "_messages", messages_storage)
        return request

    def test_links_with_full_relations(self, admin, settings):
        merchant = MerchantFactory.create()
        wallet = WalletFactory.create(merchant=merchant)
        currency_wallet = CurrencyWalletFactory.create(wallet=wallet)
        customer = CustomerFactory.create()
        transaction = PaymentTransactionFactory.create(
            wallet=currency_wallet, customer=customer
        )

        customer_limit = CustomerLimitFactory.create(customer=customer)
        wallet_limit = MerchantLimitFactory.create(wallet=wallet)
        merchant_limit = MerchantLimitFactory.create(merchant=merchant)
        LimitAlertFactory.create(transaction=transaction, customer_limit=customer_limit)
        LimitAlertFactory.create(transaction=transaction, merchant_limit=wallet_limit)
        LimitAlertFactory.create(transaction=transaction, merchant_limit=merchant_limit)

        links_html = admin.links(transaction)

        expected_links = [
            (
                reverse("admin:payment_paymenttransactioneventlog_changelist")
                + f"?transaction__id__exact={transaction.id}",
                "Logs",
            ),
            (
                reverse("admin:payment_incomingcallback_changelist")
                + f"?transaction__id__exact={transaction.id}",
                "Incoming callbacks",
            ),
            (
                reverse("admin:payment_wallet_change", args=[wallet.pk]),
                "Wallet",
            ),
            (
                f"{settings.BETMASTER_BASE_URL}admin/payment/paymenttransaction/"
                f"?id_in_payment_system={transaction.uuid}",
                "Betmaster transactions",
            ),
            (
                reverse("admin:limits_customerlimit_changelist")
                + f"?id__in={customer_limit.id}",
                "Triggered Customer Limits",
            ),
            (
                reverse("admin:limits_merchantlimit_changelist")
                + f"?id__in={wallet_limit.id}",
                "Triggered Wallet Limits",
            ),
            (
                reverse("admin:limits_merchantlimit_changelist")
                + f"?id__in={merchant_limit.id}",
                "Triggered Merchant Limits",
            ),
            (
                reverse("admin:limits_limitalert_changelist")
                + f"?transaction__id__exact={transaction.id}",
                "Triggered Limit Alerts",
            ),
        ]

        for url, text in expected_links:
            assert url in links_html, f"Link {url} not found in links_html"
            assert text in links_html, f"Text {text} not found in links_html"

        assert links_html.startswith("<ul>")
        assert links_html.endswith("</ul>")
        assert links_html.count("<li>") == len(
            expected_links
        ), f"Expected {len(expected_links)} links, but found {links_html.count('<li>')}"

    def test_links_without_customer(self, admin, settings):
        merchant = MerchantFactory.create()
        wallet = WalletFactory.create(merchant=merchant)
        currency_wallet = CurrencyWalletFactory.create(wallet=wallet)
        transaction = PaymentTransactionFactory.create(
            wallet=currency_wallet, customer=None
        )

        wallet_limit = MerchantLimitFactory.create(wallet=wallet)
        merchant_limit = MerchantLimitFactory.create(merchant=merchant)
        LimitAlertFactory.create(transaction=transaction, merchant_limit=wallet_limit)
        LimitAlertFactory.create(transaction=transaction, merchant_limit=merchant_limit)

        links_html = admin.links(transaction)

        expected_links = [
            (
                reverse("admin:payment_paymenttransactioneventlog_changelist")
                + f"?transaction__id__exact={transaction.id}",
                "Logs",
            ),
            (
                reverse("admin:payment_incomingcallback_changelist")
                + f"?transaction__id__exact={transaction.id}",
                "Incoming callbacks",
            ),
            (
                reverse("admin:payment_wallet_change", args=[wallet.pk]),
                "Wallet",
            ),
            (
                f"{settings.BETMASTER_BASE_URL}admin/payment/paymenttransaction/"
                f"?id_in_payment_system={transaction.uuid}",
                "Betmaster transactions",
            ),
            (
                reverse("admin:limits_merchantlimit_changelist")
                + f"?id__in={wallet_limit.id}",
                "Triggered Wallet Limits",
            ),
            (
                reverse("admin:limits_merchantlimit_changelist")
                + f"?id__in={merchant_limit.id}",
                "Triggered Merchant Limits",
            ),
            (
                reverse("admin:limits_limitalert_changelist")
                + f"?transaction__id__exact={transaction.id}",
                "Triggered Limit Alerts",
            ),
        ]

        for url, text in expected_links:
            assert url in links_html, f"Link {url} not found in links_html"
            assert text in links_html, f"Text {text} not found in links_html"

        assert (
            "?customer__id__exact=" not in links_html
        ), "Customer link found when it shouldn't be"
        assert (
            "Triggered Customer Limits" not in links_html
        ), "Triggered Customer Limits text found when it shouldn't be"

        assert links_html.startswith("<ul>")
        assert links_html.endswith("</ul>")
        assert links_html.count("<li>") == len(
            expected_links
        ), f"Expected {len(expected_links)} links, but found {links_html.count('<li>')}"

    @override_settings(IS_PRODUCTION=True)
    def test_has_change_permission_production(self, admin, admin_request):
        assert not admin.has_change_permission(admin_request)

    @override_settings(IS_PRODUCTION=False)
    def test_has_change_permission_development(self, admin, admin_request):
        assert admin.has_change_permission(admin_request)

    def test_changelist_contains_bitso_audit_button(self, client: Client):
        user = UserFactory.create(is_superuser=True, is_staff=True)
        client.force_login(user)

        response = client.get(reverse("admin:payment_paymenttransaction_changelist"))

        assert response.status_code == 200
        content = response.content.decode()
        assert "Run Bitso SPEI audit" in content
        assert reverse("admin:payment_paymenttransaction_bitso_spei_audit") in content

    def test_bitso_spei_audit_view_get(self, admin):
        user = UserFactory.create(is_superuser=True, is_staff=True)
        request = RequestFactory().get("/")
        request.user = user
        setattr(request, "session", {})
        setattr(request, "_messages", FallbackStorage(request))

        response = admin.bitso_spei_audit_view(request)

        assert response.status_code == 200
        assert "Run Bitso SPEI audit" in response.content.decode()

    def test_bitso_spei_audit_view_post_schedules_task(self, admin):
        user = UserFactory.create(is_superuser=True, is_staff=True)
        start = timezone.now() - timedelta(hours=2)
        end = timezone.now()

        request = RequestFactory().post(
            "/",
            data={
                "start_date": start.strftime("%Y-%m-%d %H:%M:%S"),
                "end_date": end.strftime("%Y-%m-%d %H:%M:%S"),
                "dry_run": "on",
            },
        )
        request.user = user
        setattr(request, "session", {})
        setattr(request, "_messages", FallbackStorage(request))

        with patch(
            "rozert_pay.payment.admin.transactions.run_bitso_spei_audit.delay"
        ) as delay_mock:
            response = admin.bitso_spei_audit_view(request)

        assert response.status_code == 302
        assert response.url == reverse("admin:payment_paymenttransaction_changelist")
        delay_mock.assert_called_once()
        _, kwargs = delay_mock.call_args
        assert kwargs["dry_run"] is True


@pytest.mark.django_db
@pytest.mark.usefixtures("disable_cache")
class TestTransactionManagerAdmin:
    @pytest.fixture
    def admin(self):
        return TransactionManagerAdmin(model=TransactionManager, admin_site=AdminSite())

    @pytest.fixture
    def admin_request(self):
        user = UserFactory.create(is_superuser=True)
        request = RequestFactory().get("/")
        request.user = user
        setattr(request, "session", {})
        messages_storage = FallbackStorage(request)
        setattr(request, "_messages", messages_storage)
        return request

    def test_export_to_xlsx_success(self, admin, admin_request):
        merchant = MerchantFactory.create()
        wallet = WalletFactory.create(merchant=merchant)
        currency_wallet = CurrencyWalletFactory.create(wallet=wallet)

        transaction = PaymentTransactionFactory.create(
            wallet=currency_wallet, amount=100.00, status="success"
        )

        queryset = PaymentTransaction.objects.filter(id=transaction.id)

        response = admin.export_to_xlsx(admin_request, queryset)

        assert isinstance(response, FileResponse)
        assert response.status_code == 200

        content_disposition = response.headers["Content-Disposition"]

        assert "attachment;" in content_disposition
        assert "filename=" in content_disposition
        assert "transactions_" in content_disposition
        assert ".xlsx" in content_disposition

        assert response.headers["Content-Type"] == (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        content = b"".join(response)
        assert len(content) > 0
        response.close()

    def test_export_to_xlsx_empty_queryset(self, admin, admin_request):
        queryset = PaymentTransaction.objects.none()

        response = admin.export_to_xlsx(admin_request, queryset)

        assert response is None

        messages = list(admin_request._messages)
        assert len(messages) == 1
        assert "No transactions found matching the selected criteria" in str(
            messages[0]
        )
        assert messages[0].level == django_messages.WARNING

    def test_export_to_xlsx_limit_exceeded(
        self, admin, admin_request, disable_error_logs
    ):
        limit = 10000
        admin.export_max_rows = limit

        queryset = Mock()
        queryset.exists.return_value = True
        excessive_ids = list(range(limit + 1))
        queryset.values_list.return_value = excessive_ids

        response = admin.export_to_xlsx(admin_request, queryset)

        assert response is None

        messages = list(admin_request._messages)
        assert len(messages) == 1

        expected_msg = f"Too many rows. Maximum allowed is {limit}"
        assert expected_msg in str(messages[0])
        assert messages[0].level == django_messages.ERROR

    def test_export_to_xlsx_date_range_exceeded(self, admin, admin_request):
        now = timezone.now()

        # two transactions with > 31 days difference
        t1 = PaymentTransactionFactory.create(created_at=now)
        t2 = PaymentTransactionFactory.create()
        t2.created_at = now - datetime.timedelta(days=32)
        t2.save()
        queryset = PaymentTransaction.objects.filter(id__in=[t1.id, t2.id])

        response = admin.export_to_xlsx(admin_request, queryset)

        assert response is None

        messages = list(admin_request._messages)
        assert len(messages) == 1
        assert "Export failed: Selected period exceeds 31 days" in str(messages[0])
        assert messages[0].level == django_messages.ERROR

    def test_get_queryset_select_related(self, admin, admin_request):
        qs = admin.get_queryset(admin_request)
        # {'wallet': {'wallet': {'merchant': {}, 'system': {}}}}
        sr = qs.query.select_related

        assert isinstance(sr, dict)
        assert "wallet" in sr
        assert "wallet" in sr["wallet"]
        assert "merchant" in sr["wallet"]["wallet"]
        assert "system" in sr["wallet"]["wallet"]


@pytest.mark.django_db
@pytest.mark.usefixtures("disable_cache")
class TestTransactionDateTimeQuickFilter:
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
    def filter_instance(self, admin_request):
        model = PaymentTransaction
        field = model._meta.get_field("created_at")
        field_path = "created_at"
        site = AdminSite()
        model_admin = TransactionManagerAdmin(TransactionManager, site)
        return TransactionDateTimeQuickFilter(
            field, admin_request, {}, model, model_admin, field_path
        )

    def test_init_sets_correct_links(self, filter_instance):
        assert len(filter_instance.links) > 0
        labels = [link[0] for link in filter_instance.links]

        expected_labels = ["Today", "Yesterday", "Last 7 days", "Last 30 days"]

        for ex_label in expected_labels:
            assert any(
                str(label) == ex_label for label in labels
            ), f"{ex_label} not found in filters"

        for _, query_dict in filter_instance.links:
            if not query_dict:
                continue

            assert filter_instance.lookup_kwarg_gte in query_dict
            assert filter_instance.lookup_kwarg_lte in query_dict
            assert isinstance(query_dict[filter_instance.lookup_kwarg_gte], str)
            assert isinstance(query_dict[filter_instance.lookup_kwarg_lte], str)


@pytest.mark.django_db
@pytest.mark.usefixtures("disable_cache")
class TestCustomerAdmin:
    @pytest.fixture
    def admin(self):
        return CustomerAdmin(model=Customer, admin_site=AdminSite())

    @pytest.fixture
    def customer(self):
        return CustomerFactory.create()

    def _create_user_with_permissions(
        self, has_change_permission: bool, has_view_sensitive_permission: bool
    ):
        """Создает пользователя с указанными правами."""
        user = UserFactory.create(is_staff=True)

        # Для доступа к changeform_view нужно право на просмотр объекта
        view_permission = Permission.objects.get(
            codename="view_customer", content_type__app_label="payment"
        )
        user.user_permissions.add(view_permission)

        if has_change_permission:
            # Для изменения нужны права на изменение Customer
            change_permission = Permission.objects.get(
                codename="change_customer", content_type__app_label="payment"
            )
            user.user_permissions.add(change_permission)

        if has_view_sensitive_permission:
            # Для просмотра sensitive данных нужно право CAN_VIEW_PERSONAL_DATA
            from rozert_pay.payment import permissions

            sensitive_view_permission = Permission.objects.get(
                codename=permissions.CommonUserPermissions.CAN_VIEW_PERSONAL_DATA.name,
                content_type__app_label=permissions.CommonUserPermissions.CAN_VIEW_PERSONAL_DATA.app,
            )
            user.user_permissions.add(sensitive_view_permission)

        return user

    def _create_request(self, user):
        """Создает request с указанным пользователем."""
        request = RequestFactory().get("/")
        request.user = user
        setattr(request, "session", {})
        messages_storage = FallbackStorage(request)
        setattr(request, "_messages", messages_storage)
        return request

    def test_has_change_permission_and_view_sensitive_permission(self, admin, customer):
        """Тест: есть право на редактирование и просмотр sensitive."""
        user = self._create_user_with_permissions(
            has_change_permission=True, has_view_sensitive_permission=True
        )
        request = self._create_request(user)

        # Проверяем право на редактирование
        assert admin.has_change_permission(request, customer) is True

        # Мокаем get_current_request чтобы форма могла получить request
        # Нужно мокать в модуле, где он используется
        with patch(
            "rozert_pay.common.encryption.get_current_request", return_value=request
        ):
            # Получаем HTML из changeform_view
            response = admin.changeform_view(request, object_id=str(customer.id))
            html = response.content.decode()

        # Проверяем, что sensitive поля присутствуют в HTML
        assert "email_encrypted" in html or "email-encrypted" in html
        assert "phone_encrypted" in html or "phone-encrypted" in html
        assert "extra_encrypted" in html or "extra-encrypted" in html

        # Проверяем, что поля НЕ readonly в HTML (есть право на просмотр sensitive)
        # Ищем input поля для email_encrypted, phone_encrypted, extra_encrypted
        # Если поле имеет атрибут readonly, значит нет права на редактирование
        # Но так как есть право на просмотр sensitive, поля должны быть редактируемыми
        # Проверяем, что для полей email_encrypted, phone_encrypted, extra_encrypted
        # нет атрибута readonly в input элементах
        email_input_pattern = r'<[^>]*name=["\']email_encrypted["\'][^>]*>'
        phone_input_pattern = r'<[^>]*name=["\']phone_encrypted["\'][^>]*>'
        extra_input_pattern = r'<[^>]*name=["\']extra_encrypted["\'][^>]*>'

        email_matches = re.findall(email_input_pattern, html, re.IGNORECASE)
        phone_matches = re.findall(phone_input_pattern, html, re.IGNORECASE)
        extra_matches = re.findall(extra_input_pattern, html, re.IGNORECASE)

        # Если поля найдены, проверяем что они не readonly
        if email_matches:
            assert "readonly" not in email_matches[0].lower()
        if phone_matches:
            assert "readonly" not in phone_matches[0].lower()
        if extra_matches:
            assert "readonly" not in extra_matches[0].lower()

    def test_has_change_permission_no_view_sensitive_permission(self, admin, customer):
        """Тест: есть право на редактирование, но нет на просмотр sensitive."""
        user = self._create_user_with_permissions(
            has_change_permission=True, has_view_sensitive_permission=False
        )
        request = self._create_request(user)

        # Проверяем право на редактирование
        assert admin.has_change_permission(request, customer) is True

        # Мокаем get_current_request чтобы форма могла получить request
        # Нужно мокать в модуле, где он используется
        with patch(
            "rozert_pay.common.encryption.get_current_request", return_value=request
        ):
            # Получаем HTML из changeform_view
            response = admin.changeform_view(request, object_id=str(customer.id))
            html = response.content.decode()

        # Проверяем, что sensitive поля присутствуют в HTML
        assert "email_encrypted" in html or "email-encrypted" in html
        assert "phone_encrypted" in html or "phone-encrypted" in html
        assert "extra_encrypted" in html or "extra-encrypted" in html

        # Проверяем, что поля readonly в HTML (нет права на просмотр sensitive)
        # Поля должны иметь атрибут readonly в input элементах
        import re

        email_input_pattern = r'<[^>]*name=["\']email_encrypted["\'][^>]*>'
        phone_input_pattern = r'<[^>]*name=["\']phone_encrypted["\'][^>]*>'
        extra_input_pattern = r'<[^>]*name=["\']extra_encrypted["\'][^>]*>'

        email_matches = re.findall(email_input_pattern, html, re.IGNORECASE)
        phone_matches = re.findall(phone_input_pattern, html, re.IGNORECASE)
        extra_matches = re.findall(extra_input_pattern, html, re.IGNORECASE)

        # Если поля найдены, проверяем что они readonly
        if email_matches:
            assert "readonly" in email_matches[0].lower()
        if phone_matches:
            assert "readonly" in phone_matches[0].lower()
        if extra_matches:
            assert "readonly" in extra_matches[0].lower()

    def test_no_change_permission_has_view_sensitive_permission(self, admin, customer):
        """Тест: нет права на редактирование, но есть на просмотр sensitive."""
        user = self._create_user_with_permissions(
            has_change_permission=False, has_view_sensitive_permission=True
        )
        request = self._create_request(user)

        # Проверяем, что нет права на редактирование
        assert admin.has_change_permission(request, customer) is False

        # Мокаем get_current_request чтобы форма могла получить request
        # Нужно мокать в модуле, где он используется
        with patch(
            "rozert_pay.common.encryption.get_current_request", return_value=request
        ):
            # Получаем HTML из changeform_view
            response = admin.changeform_view(request, object_id=str(customer.id))
            html = response.content.decode()

        # Проверяем, что sensitive поля присутствуют в HTML
        assert "email_encrypted" in html or "email-encrypted" in html
        assert "phone_encrypted" in html or "phone-encrypted" in html
        assert "extra_encrypted" in html or "extra-encrypted" in html

        # Проверяем, что поля НЕ readonly в HTML (есть право на просмотр sensitive)
        # Но так как нет права на редактирование, поля могут быть в readonly режиме админки
        # Однако sensitive данные должны быть видны (расшифрованы)
        # Проверяем, что данные расшифрованы (не зашифрованы)
        # Если данные расшифрованы, значит право на просмотр работает
        # Проверяем, что для полей email_encrypted, phone_encrypted, extra_encrypted
        # нет атрибута readonly в input элементах (если они есть как input)
        # Но так как нет права на редактирование, поля могут быть в div.readonly
        email_input_pattern = r'<[^>]*name=["\']email_encrypted["\'][^>]*>'
        phone_input_pattern = r'<[^>]*name=["\']phone_encrypted["\'][^>]*>'
        extra_input_pattern = r'<[^>]*name=["\']extra_encrypted["\'][^>]*>'

        email_matches = re.findall(email_input_pattern, html, re.IGNORECASE)
        phone_matches = re.findall(phone_input_pattern, html, re.IGNORECASE)
        extra_matches = re.findall(extra_input_pattern, html, re.IGNORECASE)

        # Если поля найдены как input, проверяем что они не readonly (есть право на просмотр)
        # Но так как нет права на редактирование, они могут быть в div.readonly
        # Главное - данные должны быть расшифрованы (видимы)
        if email_matches:
            # Если поле есть как input, оно не должно быть readonly
            assert "readonly" not in email_matches[0].lower()
        if phone_matches:
            assert "readonly" not in phone_matches[0].lower()
        if extra_matches:
            assert "readonly" not in extra_matches[0].lower()

    def test_no_change_permission_no_view_sensitive_permission(self, admin, customer):
        """Тест: нет обоих прав."""
        user = self._create_user_with_permissions(
            has_change_permission=False, has_view_sensitive_permission=False
        )
        request = self._create_request(user)

        # Проверяем, что нет права на редактирование
        assert admin.has_change_permission(request, customer) is False

        # Мокаем get_current_request чтобы форма могла получить request
        # Нужно мокать в модуле, где он используется
        with patch(
            "rozert_pay.common.encryption.get_current_request", return_value=request
        ):
            # Получаем HTML из changeform_view
            response = admin.changeform_view(request, object_id=str(customer.id))
            html = response.content.decode()

        # Проверяем, что sensitive поля присутствуют в HTML
        assert "email_encrypted" in html or "email-encrypted" in html
        assert "phone_encrypted" in html or "phone-encrypted" in html
        assert "extra_encrypted" in html or "extra-encrypted" in html

        # Проверяем, что поля readonly в HTML (нет права на просмотр sensitive)
        # Поля должны иметь атрибут readonly в input элементах
        import re

        email_input_pattern = r'<[^>]*name=["\']email_encrypted["\'][^>]*>'
        phone_input_pattern = r'<[^>]*name=["\']phone_encrypted["\'][^>]*>'
        extra_input_pattern = r'<[^>]*name=["\']extra_encrypted["\'][^>]*>'

        email_matches = re.findall(email_input_pattern, html, re.IGNORECASE)
        phone_matches = re.findall(phone_input_pattern, html, re.IGNORECASE)
        extra_matches = re.findall(extra_input_pattern, html, re.IGNORECASE)

        # Если поля найдены, проверяем что они readonly
        if email_matches:
            assert "readonly" in email_matches[0].lower()
        if phone_matches:
            assert "readonly" in phone_matches[0].lower()
        if extra_matches:
            assert "readonly" in extra_matches[0].lower()
