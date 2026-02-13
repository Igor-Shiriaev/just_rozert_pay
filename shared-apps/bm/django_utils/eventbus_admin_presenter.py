import json
import logging
from decimal import Decimal
from typing import Any, Callable, ClassVar, Dict, Generator, List, Optional, Type, TypeVar

from admin_customize.utils import humanize_datetime
from bm.datatypes import Money
from bm.eventbus import EventPayload, EventType
from bm.eventbus.events import Event
from bm.utils import BMJsonEncoder, instance_as_data
from django.template import loader
from django.utils.http import urlencode
from django.utils.safestring import SafeString
from pydantic import BaseModel

TEPP = TypeVar('TEPP', bound=Type['EventPayloadPresenter'])
TERELP = TypeVar('TERELP', bound=Type['EventRelatedEntityLinkPresenter'])

logger = logging.getLogger(__name__)


class EventPresenterRegistry:
    def __init__(self) -> None:
        self.__event_payload_presenters_map: Dict[str, Type['EventPayloadPresenter']] = {}
        self.__event_related_entity_link_presenters_map: Dict[
            str, Type['EventRelatedEntityLinkPresenter']
        ] = {}

    def register_event_payload_presenter(self, *event_types: EventType) -> Callable[[TEPP], TEPP]:
        def decorator(cls: TEPP) -> TEPP:
            for event_type in event_types:
                self.__event_payload_presenters_map[event_type] = cls
            return cls

        return decorator

    def register_event_related_entity_link_presenter(
        self, *event_types: EventType
    ) -> Callable[[TERELP], TERELP]:
        def decorator(cls: TERELP) -> TERELP:
            for event_type in event_types:
                self.__event_related_entity_link_presenters_map[event_type] = cls
            return cls

        return decorator

    def get_event_payload_presenter(self, event: Event) -> 'EventPayloadPresenter':
        presenter_class: Type['EventPayloadPresenter'] = self.__event_payload_presenters_map.get(
            event.event_type, EventPayloadPresenter
        )
        return presenter_class(event=event.payload)

    def get_event_related_entity_link_presenter(
        self, event: Event
    ) -> 'EventRelatedEntityLinkPresenter':
        presenter_class: Type[
            'EventRelatedEntityLinkPresenter'
        ] = self.__event_related_entity_link_presenters_map.get(
            event.event_type, EventRelatedEntityLinkPresenter
        )
        return presenter_class(event=event.payload)

    entity_link_presenter: 'EventRelatedEntityLinkPresenter'
    payload_presenter: 'EventPayloadPresenter'


presenters_registry = EventPresenterRegistry()


class EventPayloadPresenter:
    _ignored_fields = (
        'is_loadtest',
        'user_id',
        'ignore_by_promoservice',
        'priority',
        'user_currency',
    )

    def __init__(self, event: EventPayload) -> None:
        self.event: Any = event

    def payload_to_list_admin_layout(self) -> Optional[List[List[str]]]:
        return None

    def raw_payload_to_list_admin_layout(self) -> Dict[str, Any]:
        return {
            k: v for k, v in instance_as_data(self.event).items() if k not in self._ignored_fields
        }


class EventRelatedEntityLinkPresenter:
    def __init__(self, event: EventPayload) -> None:
        self.event: Any = event

    def related_entity_link(self) -> str:
        return '-'


@presenters_registry.register_event_payload_presenter(
    EventType.DEPOSIT_SUCCEEDED,
    EventType.DEPOSIT_FAILED,
    EventType.DEPOSIT_INITIATED,
    EventType.WITHDRAWAL_SUCCEEDED,
)
class PaymentEventPayloadPresenter(EventPayloadPresenter):
    def payload_to_list_admin_layout(self) -> Optional[List[List[str]]]:
        return [
            [
                f'<b>Payment system</b>: {self.event.payment_system}',
                f'<b>Amount</b>: {self.event.amount.value} <b>{self.event.amount.currency}</b>',
            ]
        ]


@presenters_registry.register_event_payload_presenter(EventType.SPORTS_BET_CHANGED)
class SportEventPayloadPresenter(EventPayloadPresenter):
    def payload_to_list_admin_layout(self) -> Optional[List[List[str]]]:
        return [
            [
                f'<b>Matches</b>: {self._get_matches_links()}',
                f'<b>State</b>: {self.event.state.value}',
                f'<b>Stake</b>: {self.event.stake.value} {self.event.stake.currency} '
                f'(Odd: {self.event.total_odds})',
            ]
        ]

    def _get_matches_links(self) -> str:
        model_link_by_provider = {
            'sr': '/admin/feed/match/',
            'pn': '/admin/feed/pinnaclematch/',
            'od': '/admin/feed/oddinmatch/',
        }
        matches = []
        for selection in self.event.selections:
            if selection.match_id is None:
                continue
            match_link = '?'.join(
                [
                    model_link_by_provider[selection.provider],
                    urlencode({'id': selection.match_id}),
                ]
            )
            matches.append(f'<a href="{match_link}">{selection.match_id}</a>')
        return ', '.join(matches)


@presenters_registry.register_event_payload_presenter(
    EventType.CASINO_ACTION_CREATED,
)
class CasinoActionEventPayloadPresenter(EventPayloadPresenter):
    def payload_to_list_admin_layout(self) -> Optional[List[List[str]]]:
        return [
            [
                f'<b>Game</b>: {self.event.game_foreign_system_id} ({self.event.game_provider})',
                f'<b>Status</b>: {self.event.action_type.value}',
                f'<b>Amount</b>: {self.event.amount.value} {self.event.amount.currency}',
            ],
        ]


@presenters_registry.register_event_related_entity_link_presenter(
    EventType.SPORTS_BET_CHANGED,
)
class SportEventEntityLinkPresenter(EventRelatedEntityLinkPresenter):
    def related_entity_link(self) -> str:
        link_url = '/admin/betmaster/bet/'
        bet_uuid_prefix = str(self.event.bet_uuid).split('-')[0]
        link = f'{link_url}?{urlencode({"q": bet_uuid_prefix})}'
        link_text = f'Bet:&nbsp;{bet_uuid_prefix}'
        return f'<a href="{link}">{link_text}</a>'


@presenters_registry.register_event_related_entity_link_presenter(
    EventType.CASINO_ACTION_CREATED,
)
class CasinoActionEntityLinkPresenter(EventRelatedEntityLinkPresenter):
    def related_entity_link(self) -> str:
        if self.event.action_id is None:  # old event
            return '-'
        link = f'/admin/casino/casinoaction/{self.event.action_id}/change/'
        link_text = 'Casino Action'
        return f'<a href="{link}">{link_text}</a>'


@presenters_registry.register_event_related_entity_link_presenter(
    EventType.DEPOSIT_INITIATED,
    EventType.DEPOSIT_SUCCEEDED,
    EventType.DEPOSIT_FAILED,
    EventType.DEPOSIT_ROLLBACKED,
    EventType.WITHDRAWAL_SUCCEEDED,
    EventType.WITHDRAWAL_INITIATED,
    EventType.WITHDRAWAL_FAILED,
    EventType.WITHDRAWAL_ROLLBACKED,
    EventType.WITHDRAWAL_CANCELLED,
    EventType.PAYMENT_TRANSACTION_CHANGED,
    EventType.PAYMENT_TRANSACTION_AMOUNT_CHANGED,
)
class PaymentEventEntityLinkPresenter(EventRelatedEntityLinkPresenter):
    def related_entity_link(self) -> str:
        if not self.event.transaction_uuid:
            return '-'
        link_url = '/admin/payment/paymenttransaction/'
        link = f'{link_url}?{urlencode({"q": self.event.transaction_uuid})}'
        link_text = f'Transaction'
        return f'<a href="{link}">{link_text}</a>'


@presenters_registry.register_event_related_entity_link_presenter(
    EventType.USER_SIGNED_IN,
    EventType.USER_SIGNED_OUT,
)
class UserSigninEventEntityLinkPresenter(EventRelatedEntityLinkPresenter):
    def related_entity_link(self) -> str:
        link_url = '/admin/betmaster/usersigninevent/'
        link = f'{link_url}?{urlencode({"id": self.event.signin_event_id})}'
        link_text = f'Sign in/out event'
        return f'<a href="{link}">{link_text}</a>'


@presenters_registry.register_event_related_entity_link_presenter(
    EventType.USER_REWARDED,
    EventType.REWARD_EXPIRED,
)
class UserRewardEventEntityLinkPresenter(EventRelatedEntityLinkPresenter):
    def related_entity_link(self) -> str:
        link_url = '/admin/rewards/reward/'
        link = f'{link_url}?{urlencode({"q": self.event.public_reward_id})}'
        link_text = f'Reward'
        return f'<a href="{link}">{link_text}</a>'


@presenters_registry.register_event_related_entity_link_presenter(
    EventType.PROMO_WALLET_EXPIRED,
)
class WalletEventEntityLinkPresenter(EventRelatedEntityLinkPresenter):
    def related_entity_link(self) -> str:
        link_url = '/admin/payment/wallet/'
        link = f'{link_url}?{urlencode({"q": self.event.wallet_account})}'
        link_text = f'Wallet'
        return f'<a href="{link}">{link_text}</a>'


@presenters_registry.register_event_related_entity_link_presenter(
    EventType.PARTICIPANT_ACCEPTED,
)
class ParticipantEventEntityLinkPresenter(EventRelatedEntityLinkPresenter):
    def related_entity_link(self) -> str:
        link_url = '/promo-admin/promotion/participant/'
        link = f'{link_url}?{urlencode({"q": self.event.user_id})}'
        link_text = f'Participant'
        return f'<a href="{link}">{link_text}</a>'


@presenters_registry.register_event_payload_presenter(EventType.BET_RESOLVED)
class BetResolvedEventPayloadPresenter(EventPayloadPresenter):
    def payload_to_list_admin_layout(self) -> Optional[List[List[str]]]:
        return [
            [
                f'<b>Source</b>: {self.event.source.value}',
                f'<b>Amount</b>: {self.event.amount.value} {self.event.amount.currency}',
            ]
        ]


@presenters_registry.register_event_payload_presenter(EventType.USER_REWARDED)
class UserRewardedEventPayloadPresenter(EventPayloadPresenter):
    def payload_to_list_admin_layout(self) -> Optional[List[List[str]]]:
        content = [
            f'<b>Campaign</b>: {self.event.campaign_internal_name}',
            f'<b>Reward type</b>: {self.event.reward_type.value}',
        ]
        if getattr(self.event.params, 'amount', None):
            content.append(
                f'<b>Amount</b>: {self.event.params.amount.value} {self.event.params.amount.currency}'
            )
        elif getattr(self.event.params, 'spin_amount', None):
            content.append(
                f'<b>Spin amount</b>: {self.event.params.spin_amount.value} {self.event.params.spin_amount.currency}'
            )
        else:
            content.append('')
        return [content]


@presenters_registry.register_event_related_entity_link_presenter(
    EventType.ADMIN_WITHDRAWAL_SUCCEEDED,
)
class AdminWithdrawalSucceededEventEntityLinkPresenter(EventRelatedEntityLinkPresenter):
    def related_entity_link(self) -> str:
        link_url = '/admin/payment/wallettransaction/'
        link = f'{link_url}?{urlencode({"id": self.event.wallet_transaction_id})}'
        link_text = 'Wallet transaction'
        return f'<a href="{link}">{link_text}</a>'


@presenters_registry.register_event_payload_presenter(EventType.ADMIN_WITHDRAWAL_SUCCEEDED)
class AdminWithdrawalSucceededEventPayloadPresenter(EventPayloadPresenter):
    def payload_to_list_admin_layout(self) -> Optional[List[List[str]]]:
        return [
            [
                f'<b>Amount</b>: {self.event.amount.value} {self.event.amount.currency}',
            ]
        ]


@presenters_registry.register_event_payload_presenter(
    EventType.RG_LOSS_LIMIT_SET,
    EventType.RG_LOSS_LIMIT_CHANGE_REQUESTED,
    EventType.RG_LOSS_LIMIT_CHANGE_REQUEST_CANCELLED,
    EventType.RG_LOSS_LIMIT_CHANGED,
    EventType.RG_LOSS_LIMIT_CANCEL_REQUESTED,
    EventType.RG_LOSS_LIMIT_CANCELED,
    EventType.RG_LOSS_LIMIT_VIOLATED,
    EventType.RG_DEPOSIT_LIMIT_SET,
    EventType.RG_DEPOSIT_LIMIT_CHANGED,
    EventType.RG_DEPOSIT_LIMIT_CANCELED,
    EventType.RG_DEPOSIT_LIMIT_VIOLATED,
    EventType.RG_DEPOSIT_LIMIT_VIOLATION_REMOVED,
    EventType.RG_ACTIVITY_LIMIT_SET,
    EventType.RG_ACTIVITY_LIMIT_CHANGED,
    EventType.RG_ACTIVITY_LIMIT_CANCELED,
    EventType.RG_TIMEOUT_SET,
    EventType.RG_TIMEOUT_CHANGED,
    EventType.RG_TIMEOUT_CANCELED,
    EventType.RG_WAGER_LIMIT_SET,
    EventType.RG_WAGER_LIMIT_CHANGED,
    EventType.RG_WAGER_LIMIT_CANCELED,
    EventType.RG_WAGER_LIMIT_VIOLATED,
    EventType.RG_SYSTEM_DEPOSIT_LIMIT_SET,
    EventType.RG_SYSTEM_DEPOSIT_LIMIT_CANCELED,
    EventType.RG_SYSTEM_NET_DEPOSIT_LIMIT_SET,
    EventType.RG_SYSTEM_NET_DEPOSIT_LIMIT_CANCELED,
)
class RGEventPayloadPresenter(EventPayloadPresenter):
    def payload_to_list_admin_layout(self) -> Optional[List[List[str]]]:
        first_col = [
            f'<p><b>Made by</b>: {self.event.made_by.value}</p>',
            f'<p><b>External Identity</b>: {self.event.external_identity}</p>',
        ]
        second_col = []
        if amount := getattr(self.event, 'amount', None):
            if isinstance(amount, Money):
                second_col.append(f'<p><b>Amount</b>: {str(amount)}</p>')
            elif isinstance(amount, Decimal):
                if currency := getattr(self.event, 'currency', None):
                    second_col.append(f'<p><b>Amount</b>: {amount} {currency}</p>')
            else:
                second_col.append(f'<p><b>Amount</b>: {amount}</p>')
        if new_amount := getattr(self.event, 'new_amount', None):
            second_col.append(f'<p><b>New Amount</b>: {new_amount.value} {new_amount.currency}</p>')

        if active_period_from := getattr(self.event, 'active_period_from', None):
            second_col.append(
                f'<p><b>Active period from</b>: {humanize_datetime(active_period_from)}</p>'
            )
        if active_period_to := getattr(self.event, 'active_period_to', None):
            second_col.append(f'<p><b>Active period to</b>: {humanize_datetime(active_period_to)}</p>')

        if active_from := getattr(self.event, 'active_from', None):
            second_col.append(f'<p><b>Active from</b>: {humanize_datetime(active_from)}</p>')
        if active_to := getattr(self.event, 'active_to', None):
            second_col.append(f'<p><b>Active to</b>: {humanize_datetime(active_to)}</p>')

        third_col = []
        if period := getattr(self.event, 'period', None):
            third_col.append(f'<p><b>Period</b>: {period}</p>')
        if product := getattr(self.event, 'product', None):
            third_col.append(f'<p><b>Product</b>: {product}</p>')

        content = [
            ''.join(first_col),
            ''.join(second_col),
            ''.join(third_col),
        ]

        return [content]


@presenters_registry.register_event_related_entity_link_presenter(
    EventType.RG_DEPOSIT_LIMIT_SET,
    EventType.RG_DEPOSIT_LIMIT_CHANGED,
    EventType.RG_DEPOSIT_LIMIT_CANCELED,
    EventType.RG_DEPOSIT_LIMIT_VIOLATED,
    EventType.RG_DEPOSIT_LIMIT_VIOLATION_REMOVED,
)
class DepositLimitEventEntityLinkPresenter(EventRelatedEntityLinkPresenter):
    def related_entity_link(self) -> str:
        link_url = '/admin/betmaster/responsiblegamblingdepositlimit/'
        link = f'{link_url}?{urlencode({"id": self.event.object_id})}'
        return f'<a href="{link}">Deposit Limit</a>'


@presenters_registry.register_event_related_entity_link_presenter(
    EventType.RG_TIMEOUT_SET,
    EventType.RG_TIMEOUT_CHANGED,
    EventType.RG_TIMEOUT_CANCELED,
)
class TimeoutEventEntityLinkPresenter(EventRelatedEntityLinkPresenter):
    def related_entity_link(self) -> str:
        link_url = '/admin/betmaster/responsiblegamblingtimeout/'
        link = f'{link_url}?{urlencode({"id": self.event.object_id})}'
        return f'<a href="{link}">Timeout</a>'


@presenters_registry.register_event_related_entity_link_presenter(
    EventType.RG_LOSS_LIMIT_SET,
    EventType.RG_LOSS_LIMIT_CHANGE_REQUESTED,
    EventType.RG_LOSS_LIMIT_CHANGE_REQUEST_CANCELLED,
    EventType.RG_LOSS_LIMIT_CHANGED,
    EventType.RG_LOSS_LIMIT_CANCEL_REQUESTED,
    EventType.RG_LOSS_LIMIT_CANCELED,
    EventType.RG_LOSS_LIMIT_VIOLATED,
    EventType.RG_ACTIVITY_LIMIT_SET,
    EventType.RG_ACTIVITY_LIMIT_CHANGED,
    EventType.RG_ACTIVITY_LIMIT_CANCELED,
    EventType.RG_WAGER_LIMIT_SET,
    EventType.RG_WAGER_LIMIT_CHANGED,
    EventType.RG_WAGER_LIMIT_CANCELED,
    EventType.RG_WAGER_LIMIT_VIOLATED,
    EventType.RG_SYSTEM_DEPOSIT_LIMIT_SET,
    EventType.RG_SYSTEM_DEPOSIT_LIMIT_CANCELED,
    EventType.RG_SYSTEM_NET_DEPOSIT_LIMIT_SET,
    EventType.RG_SYSTEM_NET_DEPOSIT_LIMIT_CANCELED,
)
class RgLimitEventEntityLinkPresenter(EventRelatedEntityLinkPresenter):
    def related_entity_link(self) -> str:
        link_url = '/admin/betmaster/rglimit/'
        link = f'{link_url}?{urlencode({"id": self.event.object_id})}'
        return f'<a href="{link}">Limit</a>'


class ListViewPayload(BaseModel):
    raw_payload: str
    event: Event
    verbose_payload: Optional[List[List[str]]] = None
    error: bool = False

    _template: ClassVar[str] = 'admin/eventbusevent/payload_listview.html'

    _columns: ClassVar[int] = 3

    @property
    def has_verbose_payload(self) -> bool:
        return self.verbose_payload is not None

    def payload_for_admin(self) -> str:
        return json.dumps(
            self.event.payload.get_repr_with_masked_private_data(), indent=4, cls=BMJsonEncoder
        )

    @property
    def table_width(self) -> int:
        if self.verbose_payload is None:
            raise ValueError('verbose_payload is None')
        return max(len(row) for row in self.verbose_payload)

    @classmethod
    def from_payload(cls, event: Event) -> 'ListViewPayload':
        presenter = presenters_registry.get_event_payload_presenter(event)
        raw_payload = presenter.raw_payload_to_list_admin_layout()
        error = False
        try:
            verbose_payload = presenter.payload_to_list_admin_layout()
        except Exception:
            logger.exception('Error while rendering payload for event', extra={'event': event})
            verbose_payload = None
            error = True

        return cls(
            raw_payload=json.dumps(raw_payload, indent=4, cls=BMJsonEncoder),
            verbose_payload=verbose_payload,
            error=error,
            event=event,
        )

    def render_list(self) -> SafeString:
        t = loader.get_template(self._template)
        return t.render(context={'data': self})

    def render_detailed(self) -> str:
        return self.payload_for_admin()

    def get_verbose_payload(self) -> Optional[Generator[List[str], None, None]]:
        if self.verbose_payload is None:
            return None

        for row in self.verbose_payload:
            if len(row) > self._columns:
                raise ValueError(f'Row {row} has more than {self._columns} columns')
            if len(row) < self._columns:
                row.extend([''] * (self._columns - len(row)))
            yield row

        return None

