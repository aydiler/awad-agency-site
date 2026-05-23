/**
 * Awad Agency — Form Submission Handler
 *
 * Sends form data to a Google Apps Script web app endpoint.
 * Works with any <form class="quote-form"> on the site.
 *
 * SETUP: Replace the URL below with your deployed Apps Script URL.
 */

var FORM_URL = 'https://api.web3forms.com/submit';
var FORM_KEY = 'd8096bb2-740d-4b94-9453-49744e70f986';

(function () {
  'use strict';

  document.addEventListener('DOMContentLoaded', function () {
    var forms = document.querySelectorAll('.quote-form');
    for (var i = 0; i < forms.length; i++) {
      forms[i].addEventListener('submit', handleSubmit);
    }

    // Track click-to-call events for GA4 + GTM
    var callBtns = document.querySelectorAll('a[href^="tel:"]');
    for (var j = 0; j < callBtns.length; j++) {
      callBtns[j].addEventListener('click', function () {
        if (window.dataLayer) {
          window.dataLayer.push({ event: 'call_button_click', source: window.location.pathname });
        }
        if (window.gtag) {
          // beacon transport — survives the navigation when dialer opens
          window.gtag('event', 'phone_click', { source: window.location.pathname, transport_type: 'beacon' });
        }
      });
    }
  });

  function handleSubmit(e) {
    e.preventDefault();

    var form = e.target;
    var btn = form.querySelector('.form-submit');
    var status = form.querySelector('.form-status');

    // Basic client-side validation
    var name = form.querySelector('[name="name"]');
    var email = form.querySelector('[name="email"]');
    var phone = form.querySelector('[name="phone"]');

    if (name && !name.value.trim()) {
      showStatus(status, 'Please enter your name.', 'error');
      name.focus();
      return;
    }
    if (email && !isValidEmail(email.value)) {
      showStatus(status, 'Please enter a valid email address.', 'error');
      email.focus();
      return;
    }
    if (phone && !isValidPhone(phone.value)) {
      showStatus(status, 'Please enter a valid phone number.', 'error');
      phone.focus();
      return;
    }

    // Honeypot check (spam prevention)
    var honeypot = form.querySelector('[name="website"]');
    if (honeypot && honeypot.value) {
      // Bot filled hidden field — silently discard
      showStatus(status, 'Thank you! We\'ll be in touch soon.', 'success');
      form.reset();
      return;
    }

    // Disable button and show loading
    btn.disabled = true;
    btn.setAttribute('data-original', btn.textContent);
    btn.textContent = 'Sending...';
    showStatus(status, '', '');

    // Collect form data
    var data = {
      name: val(form, 'name'),
      email: val(form, 'email'),
      phone: val(form, 'phone'),
      insuranceType: val(form, 'insuranceType'),
      message: val(form, 'message'),
      source: window.location.pathname
    };

    // Send to Web3Forms
    data.access_key = FORM_KEY;
    data.subject = 'New Quote Request — ' + (data.insuranceType || 'Insurance');

    fetch(FORM_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    })
    .then(function (res) { return res.json(); })
    .then(function (result) {
      if (!result.success) throw new Error(result.message);
      showStatus(status, 'Thank you! We\'ll be in touch soon.', 'success');
      form.reset();
      // Push user-provided data for Enhanced Conversions for Leads (ECL).
      // Google's tag picks this up automatically when ECL is enabled on the customer.
      var nameParts = (data.name || '').trim().split(/\s+/);
      if (window.dataLayer) {
        window.dataLayer.push({
          event: 'set_user_data',
          user_data: {
            email: (data.email || '').trim().toLowerCase(),
            phone_number: (data.phone || '').replace(/[^0-9+]/g, ''),
            address: {
              first_name: nameParts[0] || '',
              last_name: nameParts.slice(1).join(' ') || '',
            },
          },
        });
      }

      // Track conversion in GTM/GA4 if dataLayer exists
      if (window.dataLayer) {
        window.dataLayer.push({
          event: 'form_submission',
          form_type: data.insuranceType || 'general',
          form_source: data.source
        });
      }
      // GA4: fire as recommended generate_lead event (beacon survives navigation)
      if (window.gtag) {
        window.gtag('event', 'generate_lead', {
          form_type: data.insuranceType || 'general',
          form_source: data.source,
          value: 50,
          currency: 'USD',
          transport_type: 'beacon'
        });
      }
    })
    .catch(function () {
      showStatus(status, 'Something went wrong. Please call us at (734) 304-0466.', 'error');
    })
    .finally(function () {
      btn.disabled = false;
      btn.textContent = btn.getAttribute('data-original');
    });
  }

  function val(form, name) {
    var el = form.querySelector('[name="' + name + '"]');
    return el ? el.value.trim() : '';
  }

  function isValidEmail(email) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim());
  }

  function isValidPhone(phone) {
    // Accept 7+ digits (with optional formatting chars)
    return phone.trim().replace(/[\s\-().+]/g, '').length >= 7;
  }

  function showStatus(el, message, type) {
    if (!el) return;
    el.textContent = message;
    el.className = 'form-status' + (type ? ' form-status--' + type : '');
  }
})();
