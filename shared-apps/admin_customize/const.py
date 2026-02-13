from django.utils.safestring import SafeString

IMG_YES = '<img src="/static/admin/img/icon-yes.svg" alt="True">'
IMG_NO = '<img src="/static/admin/img/icon-no.svg" alt="False">'
IMG_YES_WARN = '<img src="/static/admin/img/icon-yes-outdated.svg" alt="False">'
IMG_YES_TIME = '<img src="/static/admin/img/icon-yes-wait.svg" alt="False">'
IMG_UNKNOWN = '<img src="/static/admin/img/icon-unknown.svg" alt="False">'


def get_bool_icon(value: bool) -> SafeString:
    return SafeString(IMG_YES if value else IMG_NO)


NULL_CHOICE = (None, '---------')
