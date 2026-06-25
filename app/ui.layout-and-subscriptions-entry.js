// Global UI behavior: layout + subscription entry buttons
// 1. API base: distinguish local development from production
(function() {
  if (location.hostname === 'localhost' || location.hostname === '127.0.0.1') {
    window.API_BASE_URL = 'http://127.0.0.1:8008';
  } else {
    window.API_BASE_URL = '';
  }
})();

// 2. Sidebar width drag script
(function() {
  function setupSidebarResizer() {
    // Treat narrow screens consistently: below 1024px the sidebar overlays and is not resizable.
    if (window.innerWidth < 1024) return;
    if (document.getElementById('sidebar-resizer')) return;

    var resizer = document.createElement('div');
    resizer.id = 'sidebar-resizer';
    document.body.appendChild(resizer);

    var dragging = false;

    resizer.addEventListener('mousedown', function (e) {
      dragging = true;
      document.body.classList.add('sidebar-resizing');
      e.preventDefault();
    });

    window.addEventListener('mousemove', function (e) {
      if (!dragging) return;
      var styles = getComputedStyle(document.documentElement);
      var min =
        parseInt(styles.getPropertyValue('--sidebar-min-width')) || 180;
      var max =
        parseInt(styles.getPropertyValue('--sidebar-max-width')) || 480;
      var newWidth = e.clientX;
      if (newWidth < min) newWidth = min;
      if (newWidth > max) newWidth = max;
      document.documentElement.style.setProperty(
        '--sidebar-width',
        newWidth + 'px',
      );
      // Keep the active indicator width in sync.
      if (window.syncSidebarActiveIndicator) {
        window.syncSidebarActiveIndicator({ animate: false });
      }
    });

    window.addEventListener('mouseup', function () {
      dragging = false;
      document.body.classList.remove('sidebar-resizing');
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', setupSidebarResizer);
  } else {
    setupSidebarResizer();
  }

  var resizeTimer = null;
  // Sidebar auto-collapse threshold; keep in sync with docsify-plugin.js.
  var SIDEBAR_COLLAPSE_THRESHOLD = 1024;
  // Track the previous viewport state to avoid repeated toggles.
  var lastWasWide = window.innerWidth >= SIDEBAR_COLLAPSE_THRESHOLD;

  // Initialize sidebar state from viewport width.
  function initSidebarState() {
    var body = document.body;
    if (window.innerWidth < SIDEBAR_COLLAPSE_THRESHOLD) {
      // On small screens, keep the sidebar collapsed by default. Docsify uses `close` for expanded.
      if (body.classList.contains('close')) {
        body.classList.remove('close');
      }
    }
  }

  // Initialize sidebar state after DOM is ready.
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initSidebarState);
  } else {
    initSidebarState();
  }

  window.addEventListener('resize', function () {
    var resizer = document.getElementById('sidebar-resizer');
    if (window.innerWidth < 1024) {
      if (resizer) resizer.style.display = 'none';
    } else {
      if (resizer) {
        resizer.style.display = 'block';
      } else {
        setupSidebarResizer();
      }
    }

    // Sync sidebar expanded/collapsed state from viewport width.
    // Desktop: body.close = collapsed. Mobile: body.close = expanded, per Docsify semantics.
    var isWide = window.innerWidth >= SIDEBAR_COLLAPSE_THRESHOLD;
    var body = document.body;
    if (isWide !== lastWasWide) {
      if (isWide) {
        // Wide viewport: expand sidebar.
        if (body.classList.contains('close')) {
          body.classList.remove('close');
        }
      } else {
        // Narrow viewport: default to collapsed in Docsify mobile semantics.
        if (body.classList.contains('close')) {
          body.classList.remove('close');
        }
      }
      lastWasWide = isWide;
    }

    // Immediately sync active indicator dimensions.
    if (window.syncSidebarActiveIndicator) {
      window.syncSidebarActiveIndicator({ animate: false });
    }

    // Disable transitions during resize for smoother controls.
    document.body.classList.add('dpr-resizing');
    if (resizeTimer) {
      clearTimeout(resizeTimer);
    }
    resizeTimer = setTimeout(function () {
      document.body.classList.remove('dpr-resizing');
      resizeTimer = null;
    }, 150);
  });
})();

// 3. Custom subscription management entry button.
(function() {
  function createCustomButton() {
    if (document.getElementById('custom-toggle-btn')) return;

    var sidebarToggle = document.querySelector('.sidebar-toggle');
    if (!sidebarToggle) {
      setTimeout(createCustomButton, 100);
      return;
    }

    var btn = document.createElement('button');
    btn.id = 'custom-toggle-btn';
    btn.className = 'custom-toggle-btn';
    btn.innerHTML = '⚙️';
    btn.title = 'Admin';

    btn.addEventListener('click', function () {
      var event = new CustomEvent('ensure-arxiv-ui');
      document.dispatchEvent(event);

      setTimeout(function () {
        var loadEvent = new CustomEvent('load-arxiv-subscriptions');
        document.dispatchEvent(loadEvent);

        var overlay = document.getElementById('arxiv-search-overlay');
        if (overlay) {
          overlay.style.display = 'flex';
          requestAnimationFrame(function () {
            requestAnimationFrame(function () {
              overlay.classList.add('show');
            });
          });
        }
      }, 100);
    });

    document.body.appendChild(btn);
  }

  // Keep an independent launcher for the lower-left quick-run button.
  function createQuickRunButton() {
    if (document.getElementById('custom-quick-run-btn')) return;

    function requestQuickRunPanel() {
      window.__dprQuickRunOpenRequested = true;

      if (window.PrivateDiscussionChat && typeof window.PrivateDiscussionChat.openQuickRunPanel === 'function') {
        const opened = window.PrivateDiscussionChat.openQuickRunPanel();
        if (opened) {
          window.__dprQuickRunOpenRequested = false;
          return;
        }
      }

      if (window.DPRWorkflowRunner && typeof window.DPRWorkflowRunner.open === 'function') {
        window.__dprQuickRunOpenRequested = false;
        window.DPRWorkflowRunner.open();
        return;
      }

      var event = new CustomEvent('dpr-open-quick-run');
      document.dispatchEvent(event);
    }

    var quickBtn = document.createElement('button');
    quickBtn.id = 'custom-quick-run-btn';
    quickBtn.className = 'custom-toggle-btn custom-quick-run-btn';
    quickBtn.innerHTML = '🚀';
    quickBtn.title = 'Quick Run';
    quickBtn.setAttribute('aria-label', 'Quick Run');

    quickBtn.addEventListener('click', function (e) {
      e.preventDefault();
      e.stopPropagation();
      requestQuickRunPanel();
    });

    document.body.appendChild(quickBtn);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', createCustomButton);
  } else {
    createCustomButton();
  }
})();
