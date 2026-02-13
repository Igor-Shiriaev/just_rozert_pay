from typing import Any, Optional, TYPE_CHECKING

from django import forms

if TYPE_CHECKING:
    from bm.promotion.constants import RewardType


class CasinoRewardConfigWidget(forms.Widget):
    template_name = 'admin/casino/blocks/reward_config_field.html'

    class Media:
        js = ('https://code.jquery.com/jquery-3.4.1.min.js',)


class CasinoRewardConfigField(forms.JSONField):
    widget = CasinoRewardConfigWidget

    def __init__(
        self,
        reward_type: 'RewardType',
        base_url: str = '',
        user_currency: Optional[str] = None,
        **kwargs: Any
    ):
        self.reward_type = reward_type
        self.base_url = base_url
        self.user_currency = user_currency
        super().__init__(**kwargs)

    def widget_attrs(self, widget: forms.Widget) -> dict:
        attrs = super().widget_attrs(widget)
        if isinstance(widget, CasinoRewardConfigWidget):
            attrs['reward_type'] = self.reward_type
            attrs['base_url'] = self.base_url
            attrs['user_currency'] = self.user_currency
        return attrs
