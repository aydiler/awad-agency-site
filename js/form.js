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

// Discord lead-alert relay (AWS Lambda behind API GW). The browser pings this in parallel
// with Web3Forms so a rich alert reaches Discord; the Discord webhook stays server-side in
// the Lambda env (never exposed here). The token only deters trivial drive-by POSTs.
var RELAY_URL = 'https://nj1dfmwzv0.execute-api.eu-central-1.amazonaws.com/form';
var RELAY_TOKEN = 'awad-fwl-9f3k2';

function pingRelay(payload) {
  try {
    var body = JSON.stringify(Object.assign({ token: RELAY_TOKEN }, payload));
    // text/plain => CORS-simple request (no preflight); fire-and-forget.
    var blob = new Blob([body], { type: 'text/plain' });
    if (navigator.sendBeacon && navigator.sendBeacon(RELAY_URL, blob)) return;
    fetch(RELAY_URL, { method: 'POST', body: body, keepalive: true, mode: 'no-cors',
                       headers: { 'Content-Type': 'text/plain' } });
  } catch (e) { /* non-blocking — Web3Forms email is the source of truth */ }
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
        // GA4 phone_click + the Ads conversion fire from GTM off the dataLayer push above.
        // (GTM's Google tag adopts measurement ID G-LMQ4K045DD, so a page-level
        // gtag('event', ...) here is suppressed — GTM is the single source of truth.)
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
    // Dedup key (shared with the GTM conversion's &oid=) + ad-click id for the server-side
    // ClickConversion upload. The relay reads gclid/transaction_id from this payload.
    data.transaction_id = genTxnId();
    data.event_time = new Date().toISOString();
    var gclid = readCookie('awad_gclid');
    var gbraid = readCookie('awad_gbraid');
    var wbraid = readCookie('awad_wbraid');
    if (gclid)  data.gclid  = gclid;
    if (gbraid) data.gbraid = gbraid;
    if (wbraid) data.wbraid = wbraid;

    // Fire the Discord lead alert in parallel — independent of Web3Forms so an email
    // outage never suppresses the alert. (Bots are already filtered by the honeypot above.)
    pingRelay(data);

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

      // Notify GTM of the submission. GTM fires GA4 generate_lead + the Google Ads
      // "Quote Form Submission" conversion off this dataLayer push. (GTM's Google tag
      // adopts measurement ID G-LMQ4K045DD, so a page-level gtag('event','generate_lead')
      // would be suppressed — GTM is the single source of truth.)
      if (window.dataLayer) {
        window.dataLayer.push({
          event: 'form_submission',
          form_type: data.insuranceType || 'general',
          form_source: data.source,
          transaction_id: data.transaction_id
        });
      }
    })
    .catch(function () {
      showStatus(status, 'Something went wrong. Please call us at (313) 880-3249.', 'error');
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
