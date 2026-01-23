// CLICK_TRACKER_VERSION: 20260122_01
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

    // 遷移が絡むクリックでも落ちにくい
    p.transport_type = "beacon";

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
        // ★重要: 履歴を壊さないため、同一オリジンの通常クリックは遷移を止めない
        // new tab の場合も同様に「送るだけ」
        fire("cta_click", {
          cta_id: ctaId,
          placement: a.dataset.placement || a.dataset.place || "",
          partner: a.dataset.partner || "",
          pr: a.dataset.pr === "1" ? 1 : 0,
          link_url: href,
          link_domain: url.hostname,
        });

        // 外部に data-ga が付いているケースは稀だが、もしあるなら従来通り止めてもよい。
        // ただし現状の症状は「内部遷移」で起きているので、まずは止めない運用が安全。
        return;

      // 2) アフィ（外部導線）
      const aff = a.dataset.aff;
      if (aff) {
        const isPr = a.dataset.pr === "1";

        // /go/ や /go-pr/ が同一ドメインでもOK。遷移に負けないよう一旦止める（任意だが推奨）
        if (!newTab) e.preventDefault();

        fire("affiliate_click", {
          partner: aff,
          placement: a.dataset.place || "",
          pr: isPr ? 1 : 0,
          link_url: href,
          link_domain: url.hostname,
        }, function () {
          if (!newTab) location.href = href;
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
