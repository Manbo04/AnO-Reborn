(function () {
    "use strict";

    var STORAGE_KEY = "ano_cookie_consent"; // "accepted" | "rejected"
    var cfg = window.anoCookieConsentConfig || {};

    function getConsent() {
        try {
            return window.localStorage.getItem(STORAGE_KEY);
        } catch (e) {
            return null;
        }
    }

    function setConsent(value) {
        try {
            window.localStorage.setItem(STORAGE_KEY, value);
        } catch (e) {
            // Private browsing / storage disabled: banner will just re-show
            // next visit, which is an acceptable fallback (never load
            // trackers when we can't remember the choice).
        }
    }

    function loadAnalytics() {
        if (!cfg.gaId || window.anoAnalyticsLoaded) return;
        window.anoAnalyticsLoaded = true;

        var script = document.createElement("script");
        script.async = true;
        script.src = "https://www.googletagmanager.com/gtag/js?id=" + encodeURIComponent(cfg.gaId);
        document.head.appendChild(script);

        window.dataLayer = window.dataLayer || [];
        window.gtag = window.gtag || function () { window.dataLayer.push(arguments); };
        window.gtag("js", new Date());
        window.gtag("config", cfg.gaId);
    }

    function loadAdsense() {
        if (!cfg.adsenseClient || !cfg.showAds || window.anoAdsenseLoaded) return;
        window.anoAdsenseLoaded = true;

        var script = document.createElement("script");
        script.async = true;
        script.src = "https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js";
        script.setAttribute("data-ad-client", cfg.adsenseClient);
        document.head.appendChild(script);
    }

    function applyConsent(value) {
        if (value === "accepted") {
            loadAnalytics();
            loadAdsense();
        }
    }

    function showBanner() {
        var banner = document.getElementById("ano-cookie-consent");
        if (!banner) return;
        banner.hidden = false;

        var accept = document.getElementById("ano-cookie-accept");
        var reject = document.getElementById("ano-cookie-reject");

        if (accept) {
            accept.addEventListener("click", function () {
                setConsent("accepted");
                applyConsent("accepted");
                banner.hidden = true;
            });
        }
        if (reject) {
            reject.addEventListener("click", function () {
                setConsent("rejected");
                banner.hidden = true;
            });
        }
    }

    function init() {
        var existing = getConsent();
        if (existing) {
            applyConsent(existing);
            return;
        }
        showBanner();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
