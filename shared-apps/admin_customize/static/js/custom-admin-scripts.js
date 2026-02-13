/* global define, jQuery */
(function (factory) {
  if (typeof define === 'function' && define.amd) {
    define(['jquery'], factory)
  } else if (typeof module === 'object' && module.exports) {
    module.exports = factory(require('jquery'))
  } else {
    // Browser globals
    factory(jQuery || window.django.jQuery)
  }
}(function ($) {
  'use strict'


  $(function () {
    $('.django-select2').not('[name*=__prefix__]').djangoSelect2().addClass('django-select2-initialized');

    $(document).on('formset:added', (event, row, prefix) => {
      $(row).find('.django-select2').not('.django-select2-initialized').each((i, element) => {
        const $element = $(element);

        const $formRow = $element.closest('.form-row');

        const rowId = $formRow.attr('id').split('-').pop();

        $.each(element.attributes, function (index, attr) {
          if (attr.value && attr.value.includes('__prefix__')) {
            const newValue = attr.value.replace(/__prefix__/g, rowId);
            $element.attr(attr.name, newValue);
          }
        });

        $element.find('*').each(function () {
          $.each(this.attributes, function (index, attr) {
            if (attr.value && attr.value.includes('__prefix__')) {
              const newValue = attr.value.replace(/__prefix__/g, rowId);
              $(this).attr(attr.name, newValue);
            }
          });
        });

        if ($element.hasClass('select2-hidden-accessible')) {
          $element.select2('destroy');
        }

        try {
          $element.djangoSelect2().addClass('django-select2-initialized');
          console.log('Select2 initialized for element in row', rowId);
        } catch (e) {
          console.error('Error initializing Select2:', e, 'for element', element);
        }
      });
    });
  });


}))
