import re
from collections import defaultdict
from typing import Union

from rmq.http_client import RabbitHTTPClient
from rmq.policies.config import QueuesPoliciesByVHOSTConfiguration
from rmq.policies.const import POLICIES


def configure_policies(
    config: QueuesPoliciesByVHOSTConfiguration, rabbit_http_client: RabbitHTTPClient
) -> None:
    for vhost, policies_by_queue in config.items():
        queues_by_policies_list = defaultdict(list)

        for queue, queue_policies in policies_by_queue.items():
            queues_by_policies_list[tuple(sorted(queue_policies))].append(queue)

        for policies_list, queues in queues_by_policies_list.items():
            combined_policy_definition: dict[str, Union[int, str]] = {}
            for p in policies_list:
                combined_policy_definition.update(POLICIES[p])

            resources_pattern = '^(' + '|'.join(map(re.escape, queues)) + ')$'

            rabbit_http_client.set_policy(
                policy_name='&'.join(policies_list),
                resources_pattern=resources_pattern,
                vhost=vhost,
                policy_definition=combined_policy_definition,
                apply_to='queues',
            )
