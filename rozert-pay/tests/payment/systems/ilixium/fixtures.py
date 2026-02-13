AUTHORIZATION_FAILURE_RESPONSE = """<paymentResponse>
    <version>2</version>
    <type>AUTH</type>
    <customerId>69f10686-0d75-4d1e-9900-1b8ef75a7ea8</customerId>
    <merchant>
        <merchantId>1000064</merchantId>
        <accountId>2000134</accountId>
    </merchant>
    <transaction>
        <amount>100</amount>
        <currency>USD</currency>
        <merchantRef>c049530d</merchantRef>
        <gatewayRef>507ab0a1-63a0-4ff8-8096-3649aa64d578</gatewayRef>
        <transactionType>ECOMMERCE</transactionType>
    </transaction>
    <status>
        <code>REJECTED</code>
        <message>Duplicate merchant reference received</message>
        <reasons>
            <reason>102</reason>
        </reasons>
        <timestamp>2025-09-03T09:26:40.000Z</timestamp>
    </status>
    <paymentHistory>
        <paymentAttempt>
            <order>1</order>
            <timestamp>2025-09-03T09:24:49.000Z</timestamp>
            <code>REJECTED</code>
            <message>Currency is not enabled</message>
            <amount>100</amount>
            <currency>GBP</currency>
            <paymentMethodType>CARD</paymentMethodType>
            <token></token>
            <cardResponse>
                <validDate>092025</validDate>
                <expiryDate>022026</expiryDate>
                <cardBin>900110</cardBin>
                <cardLastFour>1112</cardLastFour>
            </cardResponse>
        </paymentAttempt>
        <paymentAttempt>
            <order>2</order>
            <timestamp>2025-09-03T09:25:38.000Z</timestamp>
            <code>REJECTED</code>
            <message>Duplicate merchant reference received</message>
            <amount>100</amount>
            <currency>USD</currency>
            <paymentMethodType>CARD</paymentMethodType>
            <token></token>
            <cardResponse>
                <validDate>092025</validDate>
                <expiryDate>022026</expiryDate>
                <cardBin>900110</cardBin>
                <cardLastFour>1112</cardLastFour>
            </cardResponse>
        </paymentAttempt>
        <paymentAttempt>
            <order>3</order>
            <timestamp>2025-09-03T09:26:40.000Z</timestamp>
            <code>REJECTED</code>
            <message>Duplicate merchant reference received</message>
            <amount>100</amount>
            <currency>USD</currency>
            <paymentMethodType>CARD</paymentMethodType>
            <token></token>
            <cardResponse>
                <validDate>092025</validDate>
                <expiryDate>022026</expiryDate>
                <cardBin>900110</cardBin>
                <cardLastFour>1112</cardLastFour>
            </cardResponse>
        </paymentAttempt>
    </paymentHistory>
</paymentResponse>"""

AUTHORIZATION_3DS_REQUIRED_RESPONSE = """<paymentResponse>
    <version>2</version>
    <type>AUTH</type>
    <customerId>69f10686-0d75-4d1e-9900-1b8ef75a7ea8</customerId>
    <merchant>
        <merchantId>1000064</merchantId>
        <accountId>2000134</accountId>
    </merchant>
    <transaction>
        <amount>100</amount>
        <currency>CAD</currency>
        <merchantRef>3b83d2d5</merchantRef>
        <gatewayRef>fc00fc26-b552-4edd-aeb3-46d8b415918f</gatewayRef>
        <transactionType>ECOMMERCE</transactionType>
    </transaction>
    <status>
        <code>PENDING</code>
        <message>3-D Secure required</message>
        <reasons>
            <reason>502</reason>
        </reasons>
        <timestamp>2025-09-03T09:28:12.000Z</timestamp>
    </status>
    <paymentHistory>
        <paymentAttempt>
            <order>1</order>
            <timestamp>2025-09-03T09:28:12.000Z</timestamp>
            <code>PENDING</code>
            <message>3-D Secure required</message>
            <amount>100</amount>
            <currency>CAD</currency>
            <paymentMethodType>CARD</paymentMethodType>
            <token></token>
            <cardResponse>
                <validDate>092025</validDate>
                <expiryDate>022026</expiryDate>
                <cardBin>900110</cardBin>
                <cardLastFour>1112</cardLastFour>
                <cardIssuingBank>3dsecure.io</cardIssuingBank>
                <cardIssuingCountry>GBR</cardIssuingCountry>
                <cardType>VISA_CREDIT</cardType>
                <cvv>NO_INFORMATION</cvv>
                <avsAddress>NO_INFORMATION</avsAddress>
                <avsPostcode>NO_INFORMATION</avsPostcode>
                <threeDSecureStatus>PENDING</threeDSecureStatus>
                <threeDSecureAcsUrl>https://pripframev2.ilixium.com/ipframe/web/threedsmethodcheck?ref=91403</threeDSecureAcsUrl>
                <threeDSecureMd>YWFzZGxtMzJrbDIzam4yYmprMmgzajRoajEybDNocjk4cXc=</threeDSecureMd>
                <threeDSecurePaReq>RU5DT0RFRF9QQVJFUQ==</threeDSecurePaReq>
            </cardResponse>
        </paymentAttempt>
    </paymentHistory>
</paymentResponse>"""

AUTHORIZATION_REJECTED_VB48_RESPONSE = """<paymentResponse>
    <version>2</version>
    <type>AUTH</type>
    <customerId>1584bffc-a0ed-448c-a960-fae4fd4e8eed</customerId>
    <merchant>
        <merchantId>4130097</merchantId>
        <accountId>4131398</accountId>
    </merchant>
    <transaction>
        <amount>100</amount>
        <currency>124</currency>
        <merchantRef>trx358456</merchantRef>
        <transactionType>ECOMMERCE</transactionType>
    </transaction>
    <status>
        <code>REJECTED</code>
        <message>Access to this functionality has been denied</message>
        <reasons>
            <reason>VB48</reason>
        </reasons>
        <timestamp>2025-09-19T12:09:30.000Z</timestamp>
    </status>
    <paymentHistory></paymentHistory>
</paymentResponse>"""

CALLBACK_DEPOSIT_SUCCESS = """

"""

HISTORY_RESPONSE = """<historyResponse>
    <status>
        <code>SUCCESS</code>
        <message>Operation successful</message>
        <timestamp>2025-09-08T08:55:46.000Z</timestamp>
    </status>
    <operation>
        <entryDate>2025-09-08T08:55:27.000Z</entryDate>
        <processedDate>2025-09-08T08:55:28.000Z</processedDate>
        <type>AUTH</type>
        <customerId>69f10686-0d75-4d1e-9900-1b8ef75a7ea8</customerId>
        <merchant>
            <merchantId>1000064</merchantId>
            <accountId>2000134</accountId>
        </merchant>
        <transaction>
            <amount>10000</amount>
            <currency>CAD</currency>
            <merchantRef>trx525</merchantRef>
            <gatewayRef>96805af1-50de-4359-92d5-8882b68e2a30</gatewayRef>
            <transactionType>CNP_ECOMMERCE</transactionType>
        </transaction>
        <status>
            <code>PENDING</code>
            <message>3-D Secure required</message>
            <reasons>
                <reason>502</reason>
            </reasons>
            <timestamp>2025-09-08T08:55:27.000Z</timestamp>
        </status>
    </operation>
    <operation>
        <entryDate>2025-09-08T08:55:41.000Z</entryDate>
        <processedDate>2025-09-08T08:55:42.000Z</processedDate>
        <type>AUTH</type>
        <customerId>69f10686-0d75-4d1e-9900-1b8ef75a7ea8</customerId>
        <merchant>
            <merchantId>1000064</merchantId>
            <accountId>2000134</accountId>
        </merchant>
        <transaction>
            <amount>10000</amount>
            <currency>CAD</currency>
            <merchantRef>trx525</merchantRef>
            <gatewayRef>96805af1-50de-4359-92d5-8882b68e2a30</gatewayRef>
            <transactionType>CNP_ECOMMERCE</transactionType>
        </transaction>
        <status>
            <code>SUCCESS</code>
            <message>Operation successful</message>
            <timestamp>2025-09-08T08:55:41.000Z</timestamp>
        </status>
    </operation>
</historyResponse>"""


THREEDS_COMPLETE_RESPONSE = """<paymentResponse>
    <version>2</version>
    <type>AUTH</type>
    <customerId>69f10686-0d75-4d1e-9900-1b8ef75a7ea8</customerId>
    <merchant>
        <merchantId>1000064</merchantId>
        <accountId>2000134</accountId>
    </merchant>
    <transaction>
        <amount>10000</amount>
        <currency>CAD</currency>
        <merchantRef>trx519</merchantRef>
        <gatewayRef>8bc993a1-b50d-4bb4-a0f8-c8ea77a8de8b</gatewayRef>
        <transactionType>ECOMMERCE</transactionType>
    </transaction>
    <status>
        <code>SUCCESS</code>
        <message>Operation successful</message>
        <timestamp>2025-09-04T11:31:36.000Z</timestamp>
    </status>
    <paymentHistory>
        <paymentAttempt>
            <order>1</order>
            <timestamp>2025-09-04T11:31:36.000Z</timestamp>
            <code>SUCCESS</code>
            <amount>10000</amount>
            <currency>CAD</currency>
            <paymentMethodType>CARD</paymentMethodType>
            <token>cd03153efad84422a17afe0561d00afc</token>
            <cardResponse>
                <acquirerRef>World Pay AcquirerRef</acquirerRef>
                <validDate>092025</validDate>
                <expiryDate>022026</expiryDate>
                <cardBin>900110</cardBin>
                <cardLastFour>1112</cardLastFour>
                <cardIssuingBank>3dsecure.io</cardIssuingBank>
                <cardIssuingCountry>GBR</cardIssuingCountry>
                <cardType>VISA_CREDIT</cardType>
                <authCode>21690</authCode>
                <cvv>MATCHED</cvv>
                <avsAddress>NOT_CHECKED</avsAddress>
                <avsPostcode>NOT_CHECKED</avsPostcode>
                <bankMid>123456</bankMid>
                <threeDSecureStatus>AUTHENTICATION_SUCCESSFUL</threeDSecureStatus>
                <threeDSecureVersion>2.2.0</threeDSecureVersion>
                <iso8583code>00</iso8583code>
            </cardResponse>
        </paymentAttempt>
    </paymentHistory>
</paymentResponse>"""

THREEDS_DECLINE_RESPONSE = """<paymentResponse>
        <type>AUTH</type>
        <status>
                <code>DECLINED</code>
                <message>Declined</message>
                <reasons>
                        <reason>1</reason>
                </reasons>
                <timestamp>2025-09-10T13:48:55.000Z</timestamp>
        </status>
        <version>2</version>
        <merchant>
                <accountId>2000134</accountId>
                <merchantId>1000064</merchantId>
        </merchant>
        <customerId>d7ab1326-b6ca-4736-acdc-894b9eeb3d66</customerId>
        <transaction>
                <amount>900</amount>
                <currency>CAD</currency>
                <gatewayRef>08f5955f-98ce-403a-973b-e95c9cd22871</gatewayRef>
                <merchantRef>trx622</merchantRef>
                <transactionType>ECOMMERCE</transactionType>
        </transaction>
        <paymentHistory>
                <paymentAttempt>
                        <code>DECLINED</code>
                        <order>1</order>
                        <token>cd03153efad84422a17afe0561d00afc</token>
                        <amount>900</amount>
                        <message>Declined</message>
                        <currency>CAD</currency>
                        <timestamp>2025-09-10T13:48:55.000Z</timestamp>
                        <cardResponse>
                                <cvv>NOT_CHECKED</cvv>
                                <bankMid>123456</bankMid>
                                <cardBin>900110</cardBin>
                                <cardType>VISA_CREDIT</cardType>
                                <validDate>092025</validDate>
                                <avsAddress>NOT_CHECKED</avsAddress>
                                <expiryDate>022026</expiryDate>
                                <acquirerRef>World Pay AcquirerRef</acquirerRef>
                                <avsPostcode>NOT_CHECKED</avsPostcode>
                                <iso8583code>05</iso8583code>
                                <cardLastFour>1112</cardLastFour>
                                <cardIssuingBank>3dsecure.io</cardIssuingBank>
                                <cardIssuingCountry>GBR</cardIssuingCountry>
                                <threeDSecureStatus>AUTHENTICATION_SUCCESSFUL</threeDSecureStatus>
                                <threeDSecureVersion>2.2.0</threeDSecureVersion>
                        </cardResponse>
                        <paymentMethodType>CARD</paymentMethodType>
                </paymentAttempt>
        </paymentHistory>
</paymentResponse>"""


CREDIT_PENDING_RESPONSE = """<paymentResponse>
    <version>2</version>
    <type>CREDIT</type>
    <customerId>69f10686-0d75-4d1e-9900-1b8ef75a7ea8</customerId>
    <merchant>
        <merchantId>1000064</merchantId>
        <accountId>2000134</accountId>
    </merchant>
    <transaction>
        <amount>10000</amount>
        <currency>CAD</currency>
        <merchantRef>trx999</merchantRef>
        <gatewayRef>gw-1234567890</gatewayRef>
        <transactionType>ECOMMERCE</transactionType>
    </transaction>
    <status>
        <code>PENDING</code>
        <message>Operation pending</message>
        <timestamp>2025-09-10T13:48:55.000Z</timestamp>
    </status>
</paymentResponse>"""


WITHDRAWAL_FAILED_RESPONSE = {
    "errors": [{"errorCode": "PA011", "errorDescription": "Field must not be blank"}],
    "paceTransactionRef": "194496",
    "status": "REJECTED",
}


WITHDRAWAL_PENDING_RESPONSE = {"paceTransactionRef": "194497", "status": "PENDING"}


WITHDRAWAL_CHECK_STATUS_RESPONSE = {
    "paymentMerchant": "BETMASTER_TEST",
    "paymentTarget": "CANADA_EFT",
    "paymentCategory": "DISBURSEMENT",
    "paymentDate": "2025-09-19",
    "paymentAmount": 1.42,
    "paymentCurrency": "CAD",
    "paymentPurposeCode": "",
    "merchantReference": "15db1fbf-fefa-4c02-8357-e073c1e7c152",
    "beneficiaryReference": "",
    "beneficiaryCompanyNumber": "",
    "beneficiaryCompanyName": "",
    "beneficiaryFirstName": "Firstname",
    "beneficiaryLastName": "Surname",
    "beneficiaryAddr1": "asdasdasdasd",
    "beneficiaryAddr2": "",
    "beneficiaryCity": "",
    "beneficiaryStateOrProvince": "",
    "beneficiaryPostcode": "AA11AA",
    "beneficiaryCountry": "",
    "beneficiaryDob": "2000-01-01",
    "beneficiaryEmailAddress": "",
    "beneficiaryPhoneNumber": "",
    "beneficiaryTaxId": "",
    "beneficiaryBankAccountType": "",
    "beneficiarySortCode": "1",
    "beneficiaryBankCode": "373",
    "beneficiaryIban": "",
    "beneficiarySwiftCode": "",
    "beneficiaryAccountNumber": "5252271",
    "beneficiaryBankCountry": "",
    "beneficiaryBankName": "",
    "beneficiaryBankAddress": "",
    "intermediaryAccountNumber": "",
    "intermediaryBankCode": "",
    "intermediaryBankSwiftCode": "",
    "intermediaryIban": "",
    "intermediateBankCountry": "",
    "paceTransactionRef": "194497",
    "status": "CONFIRMED",
}


WITHDRAWAL_CALLBACK_RESPONSE = WITHDRAWAL_PENDING_RESPONSE
