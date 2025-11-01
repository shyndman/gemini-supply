(() => {
  // Only run on the search results page
  if (window.location.pathname !== '/en/online-grocery/search') {
    return;
  }

  function applyStyle() {
    const style = document.createElement('style');
    style.textContent = 'body { background: pink !important; }';
    document.body.appendChild(style);
  }

  // Wait for DOM to be ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', applyStyle);
  } else {
    applyStyle();
  }
})();
