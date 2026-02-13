htmx.on('refreshPage', function (event) {
    htmx.ajax(
        'GET',
        window.location.href,
        {target: '#content', swap: 'outerHTML'}
    )
})
