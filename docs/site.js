// Collapse documentation navigation on small screens; retain native details controls.
const menu = document.querySelector('.sidebar details');
const narrow = window.matchMedia('(max-width: 760px)');
function adaptNavigation() { if (menu) menu.open = !narrow.matches; }
adaptNavigation();
narrow.addEventListener('change', adaptNavigation);
