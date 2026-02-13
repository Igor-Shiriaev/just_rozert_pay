(function($){
  $(document).ready(function(){
    var init = function(genericForeignKeyField, reset) {
      var $genericForeignKeyField = $(genericForeignKeyField);
      var $select = $genericForeignKeyField.find('select.vGenericForeignKeyTypeSelect');
      var $link = $genericForeignKeyField.find('a.related-lookup');
      var $input = $genericForeignKeyField.find('input.vForeignKeyRawIdAdminField');
      var update = function(reset){
        var $selectedOption = $($select[0].selectedOptions[0]);
        if (reset) {
          $input.attr('value', '').trigger('change');
        }
        if ($select.val() !== '') {
          $link.show();
          $link.attr('href', $selectedOption.attr('data-url'));
        } else {
          $link.hide();
          $link.attr('href', '#');
        }
      };
      $select.on('change', function(){
        update(true);
      });
      update(false);
    };
    var genericForeignKeyFields = $('span.vGenericForeignKeyField');
    genericForeignKeyFields.each(function(){init(this);});
    window.name = '';
  });
})(django.jQuery);
