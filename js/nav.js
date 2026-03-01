document.querySelector('.nav-toggle').addEventListener('click', function () {
  var nav = document.querySelector('.nav-bar');
  var open = nav.classList.toggle('nav-open');
  this.setAttribute('aria-expanded', open);
  this.querySelector('i').className = open ? 'fa-solid fa-xmark' : 'fa-solid fa-bars';
});
