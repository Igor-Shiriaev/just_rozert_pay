document.addEventListener('alpine:init', () => {
  Alpine.data('formPreset', () => ({
    apply(presetData) {
      if (!presetData) return;

      Object.entries(presetData).forEach(([fieldName, value]) => {
        const elements = document.getElementsByName(fieldName);

        if (!elements.length) {
          console.warn(`[Preset] Field "${fieldName}" not found.`);
          return;
        }

        elements.forEach(el => {
          this.setFieldValue(el, value);
        });
      });
    },

    setFieldValue(el, value) {
      let updated = false;

      if (el.type === 'checkbox') {
        el.checked = !!value;
        updated = true;
      } else if (el.type === 'radio') {
        if (String(el.value) === String(value)) {
          el.checked = true;
          updated = true;
        }
      } else {
        el.value = value;
        updated = true;
      }

      if (updated) {
        el.dispatchEvent(new Event('input', {bubbles: true}));
        el.dispatchEvent(new Event('change', {bubbles: true}));
      }
    },

    resetToInitial() {
      const form = this.$el.closest('form');

      if (!form) {
        console.error('[Preset] Form element not found!');
        return;
      }

      form.reset();
      const elements = form.querySelectorAll('input, select, textarea');
      elements.forEach(el => {
        if (el.type === 'button' || el.type === 'submit') return;
        this.triggerEvents(el);
      });
    },

    triggerEvents(el) {
      el.dispatchEvent(new Event('input', {bubbles: true}));
      el.dispatchEvent(new Event('change', {bubbles: true}));
    }
  }));
});
