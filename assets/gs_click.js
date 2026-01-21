// assets/ga_click.js
(function () {
  function hasGtag() {
    return typeof window.gtag === "function";
  }

  function fire(eventName, params, callback) {
    if (!hasGtag()) {
      if (callback) callback();
      return;
    }
    const p = params || {};
    if (callback) {
      p.event_callback = callback;
      p.event_timeout = 800;
    }
    window.gtag("event", eventName, p);
    if (callback) setTimeout(callback, 850);
  }

  function isNewTabClick(a, e) {
    return (
      a.target === "_blank" ||
      e.metaKey || e.ctrlKey || e.shiftKey ||
      e.button === 1
    );
  }

  document.addEventListener(
    "click",
    function (e) {
      const a = e.target.closest("a");
      if (!a || !a.href) return;

      const href = a.href;
      let url;
      try {
        url = new URL(href, location.href);
      } catch {
        return;
      }

      const sameOrigin = url.origin === location.origin;
      const newTab = isNewTabClick(a, e);

      // 1) CTA（サイト内導線）
      const ctaId = a.dataset.ga || a.dataset.cta;
      if (ctaId) {
        if (!newTab && sameOrigin) {
          e.preventDefault();
          fire("cta_click", { cta_id: ctaId, link_url: href }, function () {
            location.href = href;
          });
        } else {
          fire("cta_click", { cta_id: ctaId, link_url: href });
        }
        return;
      }

      // 2) アフィ（外部導線）
      const aff = a.dataset.aff;
      if (aff) {
        fire("affiliate_click", {
          partner: aff,
          placement: a.dataset.place || "",
          link_url: href,
          link_domain: url.hostname,
        });
        return;
      }

      // 3) その他の外部リンク
      if (!sameOrigin) {
        fire("outbound_click", {
          link_url: href,
          link_domain: url.hostname,
        });
      }
    },
    true
  );
})();
