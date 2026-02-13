document.addEventListener('DOMContentLoaded', function () {
  let popup_links = document.querySelectorAll('a[data-action="popup"]');
  for (let i = 0; i < popup_links.length; i++) {
    popup_links[i].addEventListener('click', function (e) {
      open_popup(e);
    });
  }

  function open_popup(event) {
    let new_tab = event.ctrlKey || event.metaKey;
    let url = event.target.href;
    if (!new_tab) {
      event.preventDefault();
      let get_params = new URLSearchParams(url.split('?')[1]);
      get_params.set('_popup', '1');
      url = url.split('?')[0] + '?' + get_params.toString();
      let popup = window.open(url, '_blank', 'location=no,menubar=no,status=no,toolbar=no');
      popup.focus();
    }
  }
});

