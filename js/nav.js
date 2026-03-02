document.querySelector('.nav-toggle').addEventListener('click', function () {
  var nav = document.querySelector('.nav-bar');
  var open = nav.classList.toggle('nav-open');
  this.setAttribute('aria-expanded', open);
  this.innerHTML = open
    ? '<svg class="icon icon-menu" viewBox="0 0 384 512" aria-hidden="true"><path fill="currentColor" d="M342.6 150.6c12.5-12.5 12.5-32.8 0-45.3s-32.8-12.5-45.3 0L192 210.7 86.6 105.4c-12.5-12.5-32.8-12.5-45.3 0s-12.5 32.8 0 45.3L146.7 256 41.4 361.4c-12.5 12.5-12.5 32.8 0 45.3s32.8 12.5 45.3 0L192 301.3l105.4 105.3c12.5 12.5 32.8 12.5 45.3 0s12.5-32.8 0-45.3L237.3 256l105.3-105.4z"/></svg>'
    : '<svg class="icon icon-menu" viewBox="0 0 448 512" aria-hidden="true"><path fill="currentColor" d="M0 96c0-17.7 14.3-32 32-32h384c17.7 0 32 14.3 32 32s-14.3 32-32 32H32c-17.7 0-32-14.3-32-32zm0 160c0-17.7 14.3-32 32-32h384c17.7 0 32 14.3 32 32s-14.3 32-32 32H32c-17.7 0-32-14.3-32-32zm448 160c0 17.7-14.3 32-32 32H32c-17.7 0-32-14.3-32-32s14.3-32 32-32h384c17.7 0 32 14.3 32 32z"/></svg>';
});

// Dropdown toggle
document.querySelectorAll('.dropdown-toggle').forEach(function (btn) {
  btn.addEventListener('click', function (e) {
    e.stopPropagation();
    var parent = this.closest('.has-dropdown');
    var isOpen = parent.classList.toggle('open');
    this.setAttribute('aria-expanded', isOpen);
  });
});

// Close dropdown on outside click
document.addEventListener('click', function () {
  document.querySelectorAll('.has-dropdown.open').forEach(function (el) {
    el.classList.remove('open');
    el.querySelector('.dropdown-toggle').setAttribute('aria-expanded', 'false');
  });
});
