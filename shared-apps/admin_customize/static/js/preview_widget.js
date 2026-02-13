'use strict';

function htmlDecode(input) {
    var doc = new DOMParser().parseFromString(input, "text/html");
    return doc.documentElement.textContent;
}

const preview_styles = `
* {
    line-height: initial;
}
`

function render_preview(container) {
    const previewContainer = container.querySelector('.preview_data');
    const shadowRoot = previewContainer.attachShadow({mode: 'open'});
    const sourceContainer = container.querySelector('.raw_data');
    const styles = document.createElement('style');
    styles.innerHTML = preview_styles;
    const rawHTML = htmlDecode(sourceContainer.innerHTML);
    shadowRoot.innerHTML = styles.outerHTML + rawHTML;
}

document.addEventListener('DOMContentLoaded', function () {
    const preview_containers = document.querySelectorAll('.html_preview')
    preview_containers.forEach(render_preview)
})

