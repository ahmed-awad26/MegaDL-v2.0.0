/**
 * MegaDL — router.js
 * Hash-based SPA router with page transitions and history support.
 */

MegaDL.Router = (() => {
  const { Utils } = MegaDL;

  const pages = new Map();
  let currentPage = null;
  let onNavigateCallbacks = [];

  /* ── Register page handlers ──────────────────────────────── */
  function register(pageId, { onEnter, onLeave } = {}) {
    pages.set(pageId, { onEnter, onLeave });
  }

  /* ── Navigate to page ────────────────────────────────────── */
  function navigate(pageId, pushState = true) {
    const targetEl = document.getElementById(`page-${pageId}`);
    if (!targetEl) return;

    // Deactivate current
    if (currentPage && currentPage !== pageId) {
      const prevEl = document.getElementById(`page-${currentPage}`);
      if (prevEl) prevEl.classList.remove('active');

      const prevHandler = pages.get(currentPage);
      if (prevHandler?.onLeave) prevHandler.onLeave();

      // Sync nav items
      _syncNavItems(currentPage, false);
    }

    // Activate target
    targetEl.classList.add('active');
    currentPage = pageId;

    // Trigger enter handler
    const handler = pages.get(pageId);
    if (handler?.onEnter) handler.onEnter();

    // Sync nav items
    _syncNavItems(pageId, true);

    // Update hash
    if (pushState) {
      history.pushState({ page: pageId }, '', `#${pageId}`);
    }

    // Scroll content to top
    const content = document.getElementById('main-content');
    if (content) content.scrollTo({ top: 0, behavior: 'instant' });

    // Close mobile sidebar if open
    _closeSidebar();

    // Notify callbacks
    onNavigateCallbacks.forEach(cb => cb(pageId));
  }

  /* ── Sync active state on all nav links ──────────────────── */
  function _syncNavItems(pageId, active) {
    document.querySelectorAll(`[data-page="${pageId}"]`).forEach(el => {
      el.classList.toggle('active', active);
    });
  }

  /* ── Close mobile sidebar ────────────────────────────────── */
  function _closeSidebar() {
    const sidebar  = document.getElementById('sidebar');
    const overlay  = document.getElementById('sidebar-overlay');
    sidebar?.classList.remove('open');
    overlay?.classList.remove('visible');
  }

  /* ── Hash change handler ─────────────────────────────────── */
  function _onHashChange() {
    const hash = location.hash.replace('#', '') || 'home';
    if (hash !== currentPage) navigate(hash, false);
  }

  /* ── Init ────────────────────────────────────────────────── */
  function init() {
    // Link clicks
    document.addEventListener('click', e => {
      const link = e.target.closest('[data-page]');
      if (!link) return;
      e.preventDefault();
      const pageId = link.dataset.page;
      navigate(pageId);
      Utils.haptic('light');
    });

    // Hash changes (browser back/forward)
    window.addEventListener('hashchange', _onHashChange);
    window.addEventListener('popstate', e => {
      const page = e.state?.page || location.hash.replace('#', '') || 'home';
      navigate(page, false);
    });

    // Initial navigation
    const initial = location.hash.replace('#', '') || 'home';
    navigate(initial, false);
  }

  function onNavigate(cb) {
    onNavigateCallbacks.push(cb);
  }

  function getCurrent() { return currentPage; }

  return { init, register, navigate, onNavigate, getCurrent };
})();
