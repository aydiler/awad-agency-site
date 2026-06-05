/**
 * Awad Agency — Multi-Step PPC Form
 * 4-step quote form for PPC landing pages.
 * Submits to Google Apps Script endpoint.
 */

var FORM_URL = 'https://api.web3forms.com/submit';
var FORM_KEY = 'd8096bb2-740d-4b94-9453-49744e70f986';

// Discord lead-alert relay (AWS Lambda behind API GW). Pinged in parallel with Web3Forms so
// a rich alert reaches Discord; the Discord webhook stays server-side in the Lambda env.
var RELAY_URL = 'https://nj1dfmwzv0.execute-api.eu-central-1.amazonaws.com/form';
var RELAY_TOKEN = 'awad-fwl-9f3k2';

function pingRelay(payload) {
  try {
    var body = JSON.stringify(Object.assign({ token: RELAY_TOKEN }, payload));
    var blob = new Blob([body], { type: 'text/plain' });  // text/plain => no CORS preflight
    if (navigator.sendBeacon && navigator.sendBeacon(RELAY_URL, blob)) return;
    fetch(RELAY_URL, { method: 'POST', body: body, keepalive: true, mode: 'no-cors',
                       headers: { 'Content-Type': 'text/plain' } });
  } catch (e) { /* non-blocking */ }
}

// Read a first-party cookie (e.g. awad_gclid, captured on landing — ad-blocker-proof).
function readCookie(name) {
  var m = document.cookie.match('(?:^|; )' + name + '=([^;]*)');
  return m ? decodeURIComponent(m[1]) : '';
}

// Per-submission id: shared dedup key between the GTM conversion (&oid=) and the
// server-side ClickConversion upload (order_id), so the two never double-count.
function genTxnId() {
  try {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
  } catch (e) {}
  return 'awad-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 10);
}

(function () {
  'use strict';

  var currentStep = 1;
  var totalSteps = 4;
  var formData = {};

  document.addEventListener('DOMContentLoaded', function () {
    // Step 1: ZIP + Coverage type buttons
    var typeBtns = document.querySelectorAll('.ppc-type-btn');
    for (var i = 0; i < typeBtns.length; i++) {
      typeBtns[i].addEventListener('click', function () {
        // Validate ZIP first
        var zip = document.getElementById('zipCode');
        if (!zip || !zip.value.trim() || zip.value.trim().length < 5) {
          zip.focus();
          zip.style.borderColor = '#c62828';
          setTimeout(function () { zip.style.borderColor = ''; }, 2000);
          return;
        }
        formData.zipCode = zip.value.trim();

        // Deselect all
        for (var j = 0; j < typeBtns.length; j++) {
          typeBtns[j].classList.remove('selected');
        }
        this.classList.add('selected');
        formData.insuranceType = this.getAttribute('data-type');

        // Fire micro-conversion for step 1 completion
        pushDataLayer('form_step_complete', { step: 1, type: formData.insuranceType, form_step_name: 'zip_entered' });

        // Auto-advance after short delay
        setTimeout(function () { goToStep(2); }, 300);
      });
    }

    // Next buttons
    var nextBtns = document.querySelectorAll('.ppc-btn-next');
    for (var i = 0; i < nextBtns.length; i++) {
      nextBtns[i].addEventListener('click', function () {
        var step = parseInt(this.getAttribute('data-step'));
        if (validateStep(step)) {
          collectStepData(step);
          pushDataLayer('form_step_complete', { step: step, form_step_name: step === 2 ? 'vehicle_details' : 'personal_info' });
          // Fire distinct event for step 3 (contact info = high-value micro-conversion)
          if (step === 3) {
            pushDataLayer('contact_info_provided', { form_name: 'insurance_quote' });
          }
          goToStep(step + 1);
        }
      });
    }

    // Back buttons
    var backBtns = document.querySelectorAll('.ppc-btn-back');
    for (var i = 0; i < backBtns.length; i++) {
      backBtns[i].addEventListener('click', function () {
        var step = parseInt(this.getAttribute('data-step'));
        goToStep(step - 1);
      });
    }

    // Submit
    var submitBtn = document.querySelector('.ppc-btn-submit');
    if (submitBtn) {
      submitBtn.addEventListener('click', function () {
        if (validateStep(4)) {
          collectStepData(4);
          submitForm();
        }
      });
    }

    // Track call button clicks
    var callBtns = document.querySelectorAll('a[href^="tel:"]');
    for (var i = 0; i < callBtns.length; i++) {
      callBtns[i].addEventListener('click', function () {
        pushDataLayer('call_button_click', { source: 'ppc_landing' });
      });
    }
  });

  function goToStep(step) {
    if (step < 1 || step > totalSteps) return;
    currentStep = step;

    // Show/hide steps
    var steps = document.querySelectorAll('.ppc-step');
    for (var i = 0; i < steps.length; i++) {
      steps[i].classList.remove('active');
    }
    document.querySelector('.ppc-step[data-step="' + step + '"]').classList.add('active');

    // Update progress dots
    var dots = document.querySelectorAll('.ppc-progress-dot');
    var lines = document.querySelectorAll('.ppc-progress-line');
    for (var i = 0; i < dots.length; i++) {
      dots[i].classList.remove('active', 'done');
      if (i + 1 < step) {
        dots[i].classList.add('done');
        dots[i].innerHTML = '&#10003;';
      } else if (i + 1 === step) {
        dots[i].classList.add('active');
        dots[i].textContent = i + 1;
      } else {
        dots[i].textContent = i + 1;
      }
    }
    for (var i = 0; i < lines.length; i++) {
      lines[i].classList.toggle('done', i < step - 1);
    }

    // Scroll form into view on mobile
    var wrapper = document.querySelector('.ppc-form-wrapper');
    if (wrapper && window.innerWidth < 900) {
      wrapper.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }

  function validateStep(step) {
    var stepEl = document.querySelector('.ppc-step[data-step="' + step + '"]');
    var inputs = stepEl.querySelectorAll('[required]');
    for (var i = 0; i < inputs.length; i++) {
      if (!inputs[i].value.trim()) {
        inputs[i].focus();
        inputs[i].style.borderColor = '#c62828';
        setTimeout(function () { inputs[i].style.borderColor = ''; }.bind(null, inputs[i]), 2000);
        return false;
      }
    }

    // Email validation on step 4
    if (step === 4) {
      var email = stepEl.querySelector('[name="email"]');
      if (email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.value.trim())) {
        email.focus();
        email.style.borderColor = '#c62828';
        return false;
      }
      var phone = stepEl.querySelector('[name="phone"]');
      if (phone && phone.value.trim().replace(/[\s\-().+]/g, '').length < 7) {
        phone.focus();
        phone.style.borderColor = '#c62828';
        return false;
      }
    }

    return true;
  }

  function collectStepData(step) {
    var stepEl = document.querySelector('.ppc-step[data-step="' + step + '"]');
    var inputs = stepEl.querySelectorAll('input, select');
    for (var i = 0; i < inputs.length; i++) {
      if (inputs[i].name) {
        formData[inputs[i].name] = inputs[i].value.trim();
      }
    }
  }

  function submitForm() {
    var btn = document.querySelector('.ppc-btn-submit');
    var status = document.querySelector('.ppc-status');

    btn.disabled = true;
    btn.textContent = 'Sending...';
    if (status) { status.textContent = ''; status.className = 'ppc-status'; }

    formData.source = window.location.pathname;
    // Dedup key (shared with the GTM conversion's &oid=) + ad-click id for the server-side
    // ClickConversion upload. The relay reads gclid/transaction_id from this payload.
    formData.transaction_id = genTxnId();
    formData.event_time = new Date().toISOString();
    var gclid = readCookie('awad_gclid');
    var gbraid = readCookie('awad_gbraid');
    var wbraid = readCookie('awad_wbraid');
    if (gclid)  formData.gclid  = gclid;
    if (gbraid) formData.gbraid = gbraid;
    if (wbraid) formData.wbraid = wbraid;

    // Fire the Discord lead alert in parallel — independent of Web3Forms.
    pingRelay(formData);

    formData.access_key = FORM_KEY;
    formData.subject = 'New Quote Request — ' + (formData.insuranceType || 'Insurance');

    fetch(FORM_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(formData)
    })
    .then(function (res) { return res.json(); })
    .then(function (data) {
      if (!data.success) throw new Error(data.message);
    })
    .then(function () {
      if (status) {
        status.textContent = 'Thank you! We\'ll call you shortly with your free quote.';
        status.className = 'ppc-status success';
      }
      // Push user-provided data for Enhanced Conversions for Leads (ECL).
      // Google's tag picks this up automatically when ECL is enabled on the customer.
      // Hashing happens inside Google's tag; we send plain values.
      var fullName = (formData.firstName || '') + ' ' + (formData.lastName || '');
      var userData = {
        email: (formData.email || '').trim().toLowerCase(),
        phone_number: (formData.phone || '').replace(/[^0-9+]/g, ''),
        address: {
          first_name: (formData.firstName || formData.name || '').trim(),
          last_name: (formData.lastName || '').trim(),
        },
      };
      if (window.dataLayer) {
        window.dataLayer.push({ event: 'set_user_data', user_data: userData });
      }

      // Fire conversion events
      pushDataLayer('form_submission', {
        form_type: formData.insuranceType || 'auto',
        form_source: formData.source,
        transaction_id: formData.transaction_id
      });
      pushDataLayer('quote_submitted', {
        form_name: 'insurance_quote',
        form_step: 4,
        conversion_value: 250
      });
      // Hide form, show success
      var steps = document.querySelectorAll('.ppc-step');
      for (var i = 0; i < steps.length; i++) { steps[i].style.display = 'none'; }
      var progress = document.querySelector('.ppc-progress');
      if (progress) progress.style.display = 'none';
      var header = document.querySelector('.ppc-form-header');
      if (header) {
        header.querySelector('h2').textContent = 'Quote Request Received!';
        header.querySelector('p').textContent = 'An agent will call you shortly to discuss your quote.';
      }
      btn.style.display = 'none';
    })
    .catch(function () {
      if (status) {
        status.textContent = 'Something went wrong. Please call us at (313) 880-3249.';
        status.className = 'ppc-status error';
      }
    })
    .finally(function () {
      btn.disabled = false;
      btn.textContent = 'Get My Free Quote';
    });
  }

  function pushDataLayer(event, params) {
    // GTM listens for {event: name, ...} object pushes and fires the matching GA4 events
    // (generate_lead, form_step_complete, form_step_3_complete, phone_click) AND Google Ads
    // conversion tags. GTM's Google tag adopts measurement ID G-LMQ4K045DD, so a page-level
    // gtag('event', ...) here would be suppressed — GTM is the single source of truth.
    if (window.dataLayer) {
      var data = { event: event };
      if (params) {
        for (var key in params) {
          data[key] = params[key];
        }
      }
      window.dataLayer.push(data);
    }
  }
})();
