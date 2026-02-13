import logging
from unittest.mock import Mock, patch

import pytest
import requests
from rozert_pay.payment.models import Bank, PaymentCardBank
from rozert_pay.payment.systems.bitso_spei.models import BitsoSpeiCardBank
from rozert_pay.payment.tasks import check_bitso_spei_bank_codes




