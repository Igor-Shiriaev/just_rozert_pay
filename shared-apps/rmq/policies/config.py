from collections.abc import ItemsView, KeysView
from typing import Union

from pydantic import BaseModel, validator
from rmq.policies.const import POLICIES, PolicyName


class QueuesPoliciesConfiguration(BaseModel):
    __root__: dict[str, list[PolicyName]]

    def keys(self) -> KeysView[str]:
        return self.__root__.keys()

    def items(self) -> ItemsView[str, list[PolicyName]]:
        return self.__root__.items()

    def __getitem__(self, item: str) -> list[PolicyName]:
        return self.__root__[item]


class QueuesPoliciesByVHOSTConfiguration(BaseModel):
    __root__: dict[str, QueuesPoliciesConfiguration]

    def keys(self) -> KeysView[str]:
        return self.__root__.keys()

    def items(self) -> ItemsView[str, QueuesPoliciesConfiguration]:
        return self.__root__.items()

    def __getitem__(self, item: str) -> QueuesPoliciesConfiguration:
        return self.__root__[item]

    @validator('__root__')
    def validate_policies_statements_not_overlap(cls, config: dict) -> dict:
        for vhost, policies_by_queue in config.items():
            for queue, queue_policies in policies_by_queue.items():
                # https://www.rabbitmq.com/parameters.html#combining-policy-definitions
                combined_policy_keys: set[tuple[str, Union[int, str]]] = set()

                for policy_name in queue_policies:
                    for policy_key in POLICIES[policy_name].items():
                        if policy_key in combined_policy_keys:
                            raise ValueError(
                                f'Policies statements for queue {vhost}/{queue} '
                                f'have overlapping parameter {policy_key}. '
                                'Since we declare policies with explicit priorities '
                                'please do not combine overlapping policy statements.'
                            )
                        combined_policy_keys.add(policy_key)
        return config
