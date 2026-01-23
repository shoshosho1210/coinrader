// CLICK_TRACKER_VERSION: 20260122_02
(function () {
  function hasGtag() {
    return typeof window.gtag === "function";
  }

  function once(fn) {
    let done = false;
    return function () {
      if (done) return;
      done = true;
      try { fn && fn(); } catch (_) {}
    };
  }

  function fire(eventName, params, callback) {
    const cb = callback ? once(callback) : null;

    if (!hasGtag()) {
      if (cb) cb();
      return;
    }

    const p = params || {};
    p.transport_type = "beacon";

    if (cb) {
      p.event_callback = cb;
      p.event_timeout = 800;
    }

    window.gtag("event", eventName, p);

    // 保険（event_callbackが呼ばれない環境向け）※必ず1回だけ
    if (cb) setTimeout(cb, 850);
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
        // ★重要: 同一オリジンの通常クリックは遷移を止めない（履歴が安定）
        fire("cta_click", {
          cta_id: ctaId,
          placement: a.dataset.placement || a.dataset.place || "",
          partner: a.dataset.partner || "",
          pr: a.dataset.pr === "1" ? 1 : 0,
          link_url: href,
          link_domain: url.hostname,
        });

        // 外部CTAを同一タブで踏ませる設計の場合だけ止める（基本は止めないでOK）
        // if (!sameOrigin && !newTab) { ... } ←必要ならここに入れる
        return;
      }

      // 2) アフィ（外部導線）
      const aff = a.dataset.aff;
      if (aff) {
        const isPr = a.dataset.pr === "1";

        // 同一タブで外へ飛ばす場合は止めてOK（計測優先）
        if (!newTab) e.preventDefault();

        fire(
          "affiliate_click",
          {
            partner: aff,
            placement: a.dataset.place || "",
            pr: isPr ? 1 : 0,
            link_url: href,
            link_domain: url.hostname,
          },
          function () {
            if (!newTab) location.href = href;
          }
        );
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
