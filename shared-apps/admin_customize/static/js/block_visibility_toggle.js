document.addEventListener('DOMContentLoaded', function () {
    const data_role_prefix = 'toggle-visible-'
    let toggle_triggers = document.querySelectorAll(`[data-role^="${data_role_prefix}trigger"]`);
    for (let trigger of toggle_triggers) {
        trigger.innerHTML = `<span data-role="${data_role_prefix}label">Show</span>&nbsp;${trigger.innerHTML}`
        trigger.addEventListener('click', function (e) {
            toggle_visibility(e);
        });
    }

    function toggle_visibility(event) {
        let target = event.target.dataset.role.includes('label') ? event.target.parentElement : event.target;

        let label = target.querySelector(`[data-role="${data_role_prefix}label"]`);

        let related_toggle_target = target.closest(`[data-role="${data_role_prefix}container"]`).querySelector(`[data-role="${data_role_prefix}target"]`);
        let visible_display_option = related_toggle_target.getAttribute('data-display-option') || 'block';

        if (related_toggle_target.style.display === 'none') {
            related_toggle_target.style.display = visible_display_option;
            label.innerText = 'Hide';
        } else {
            related_toggle_target.style.display = 'none';
            label.innerText = 'Show';
        }
    }
})
