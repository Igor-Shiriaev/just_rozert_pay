import pytest

from rmq.policies.config import QueuesPoliciesByVHOSTConfiguration
from rmq.policies.const import PolicyName


class TestValidatePoliciesStatementsNotOverlap:
    def test_when_overlap(self):
        with pytest.raises(ValueError) as e:
            QueuesPoliciesByVHOSTConfiguration.parse_obj(
                {
                    '/vhost-1': {
                        'queue-1': [
                            PolicyName.TTL_3_DAY,
                            PolicyName.TTL_3_DAY,
                            PolicyName.HA_EXACTLY_2,
                        ]
                    }
                }
            )

        assert (
            "Policies statements for queue /vhost-1/queue-1 have overlapping parameter ('message-ttl', 259200000)"
            in str(e.value)
        )

    def test_when_not_overlap(self):
        QueuesPoliciesByVHOSTConfiguration.parse_obj(
            {
                '/vhost-1': {
                    'queue-1': [
                        PolicyName.TTL_3_DAY,
                        PolicyName.HA_EXACTLY_2,
                    ]
                }
            }
        )
