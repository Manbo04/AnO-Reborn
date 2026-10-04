/**
 * Command Briefing — the in-game guided tour for new nations.
 * Server side: app_core/tutorial/tour.py (+ /api/tour/* in app_core/tutorial/routes.py).
 * Loaded by templates/partials/command_tour.html only while session["tour_active"] is set.
 */
(function () {
    "use strict";

    var root = document.getElementById("command-briefing");
    if (!root) return;

    var NATION = root.getAttribute("data-nation") || "your nation";
    var FLAG = root.getAttribute("data-flag") || "";
    var MIN_KEY = "ano_briefing_min";
    var csrf = (document.querySelector('meta[name="csrf-token"]') || {}).content || "";
    var state = null;
    var spotEl = null, tipEl = null, spotTarget = null, spotRaf = 0;

    function el(tag, cls, html) {
        var e = document.createElement(tag);
        if (cls) e.className = cls;
        if (html != null) e.innerHTML = html;
        return e;
    }
    function esc(s) {
        return String(s).replace(/[&<>"']/g, function (c) {
            return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
        });
    }
    function fmtReward(r) {
        var out = [];
        Object.keys(r || {}).forEach(function (k) {
            var n = Number(r[k] || 0).toLocaleString("en-US");
            out.push(k === "money" ? "+$" + n : "+" + n + " " + k);
        });
        return out;
    }
    function chips(r) {
        return fmtReward(r).map(function (t) { return '<span class="cb-chip">' + esc(t) + "</span>"; }).join("");
    }
    function api(path, body) {
        var opts = { credentials: "same-origin", headers: { "X-CSRFToken": csrf } };
        if (body) {
            opts.method = "POST";
            opts.headers["Content-Type"] = "application/json";
            opts.body = JSON.stringify(body);
        }
        return fetch(path, opts).then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; });
    }
    function getMin() { try { return localStorage.getItem(MIN_KEY) === "1"; } catch (e) { return false; } }
    function setMin(v) { try { localStorage.setItem(MIN_KEY, v ? "1" : "0"); } catch (e) {} }
    function onPage(step) {
        var p = location.pathname;
        if (step.match === "/province/") return p.indexOf("/province/") === 0;
        return p === step.match || p.indexOf(step.match + "/") === 0;
    }

    /* ---------- spotlight ---------- */
    function visibleMatch(selector) {
        var list;
        try { list = document.querySelectorAll(selector); } catch (e) { return null; }
        for (var i = 0; i < list.length; i++) {
            var r = list[i].getBoundingClientRect();
            if (r.width > 0 && r.height > 0) return list[i];
        }
        return null;
    }
    function clearSpot() {
        cancelAnimationFrame(spotRaf);
        spotTarget = null;
        if (spotEl) spotEl.classList.remove("on");
        if (tipEl) tipEl.classList.remove("on");
    }
    function spotlight(step) {
        var target = visibleMatch(step.target);
        if (!target) return false;
        // Building/unit buy buttons: pre-fill "1" in the amount box next to them.
        var box = target.closest(".purchasemilitarydiv, form, .menudiv");
        var amount = box && box.querySelector('input[type="number"]');
        if (amount && !amount.value) amount.value = "1";
        if (!spotEl) {
            spotEl = el("div", "cb-spot"); tipEl = el("div", "cb-tip");
            root.appendChild(spotEl); root.appendChild(tipEl);
        }
        tipEl.textContent = step.kind === "state"
            ? (amount ? "Amount is set to 1. Press this to build it." : "Press this to do it.")
            : "This is it. Take a look around.";
        spotTarget = target;
        target.scrollIntoView({ behavior: "smooth", block: "center" });
        (function follow() {
            if (!spotTarget) return;
            var r = spotTarget.getBoundingClientRect(), pad = 6;
            spotEl.style.left = (r.left - pad) + "px"; spotEl.style.top = (r.top - pad) + "px";
            spotEl.style.width = (r.width + pad * 2) + "px"; spotEl.style.height = (r.height + pad * 2) + "px";
            var tipTop = r.top - tipEl.offsetHeight - 14;
            if (tipTop < 70) tipTop = r.bottom + 14;
            tipEl.style.top = tipTop + "px";
            tipEl.style.left = Math.max(10, Math.min(window.innerWidth - tipEl.offsetWidth - 10, r.left)) + "px";
            spotEl.classList.add("on"); tipEl.classList.add("on");
            spotRaf = requestAnimationFrame(follow);
        })();
        target.addEventListener("click", clearSpot, { once: true });
        return true;
    }
    document.addEventListener("keydown", function (e) { if (e.key === "Escape") clearSpot(); });

    /* ---------- card ---------- */
    var card = el("section", "cb-card");
    card.setAttribute("aria-label", "Command briefing");
    var pill = el("button", "cb-pill");
    pill.type = "button";
    root.appendChild(card); root.appendChild(pill);

    function renderCard() {
        if (!state || state.current == null) { card.classList.remove("on"); pill.classList.remove("on"); return; }
        var step = state.steps[state.current], here = onPage(step);
        var segs = state.steps.map(function (s, i) {
            return '<i class="' + (s.done ? "done" : i === state.current ? "cur" : "") + '"></i>';
        }).join("");
        var primary = here
            ? (step.kind === "state" ? '<button type="button" class="cb-btn" data-cb="show">Show me ▸</button>' : '<span class="cb-label">Look around · completing…</span>')
            : '<a class="cb-btn" href="' + esc(step.href) + '">Take me there ▸</a>';
        card.innerHTML =
            '<div class="cb-head"><span class="cb-label">Command briefing · ' + (state.current + 1) + "/" + state.total + "</span>" +
            '<button type="button" class="cb-icon" data-cb="min" aria-label="Minimize briefing">–</button></div>' +
            '<div class="cb-segs" style="grid-template-columns:repeat(' + state.total + ',1fr)">' + segs + "</div>" +
            '<div class="cb-body"><h3 class="cb-title">' + esc(step.title) + '</h3><p class="cb-brief">' + esc(step.brief) + "</p>" +
            '<div class="cb-reward">' + chips(step.reward) + "</div>" +
            '<div class="cb-actions">' + primary + '<button type="button" class="cb-link" data-cb="end">End briefing</button></div></div>';
        pill.innerHTML = "<i></i>Briefing <b>" + (state.current + 1) + "/" + state.total + "</b>";
        var min = getMin();
        card.classList.toggle("on", !min);
        pill.classList.toggle("on", min);
    }
    card.addEventListener("click", function (e) {
        var b = e.target.closest("[data-cb]");
        if (!b) return;
        var act = b.getAttribute("data-cb");
        if (act === "min") { setMin(true); clearSpot(); renderCard(); }
        else if (act === "show") {
            if (!spotlight(state.steps[state.current])) {
                b.textContent = "Scroll down to find it";
            }
        } else if (act === "end") {
            if (b.classList.contains("warn")) {
                api("/api/tour/dismiss", {}).then(function () { clearSpot(); root.remove(); });
            } else {
                b.classList.add("warn"); b.textContent = "Tap again to end (rewards stop)";
                setTimeout(function () { if (b.isConnected) { b.classList.remove("warn"); b.textContent = "End briefing"; } }, 4000);
            }
        }
    });
    pill.addEventListener("click", function () { setMin(false); renderCard(); });

    /* ---------- toasts / overlays ---------- */
    function toast(item) {
        var t = el("div", "cb-toast",
            '<div class="cb-label">Mission complete</div><div class="cb-title">' + esc(item.title) + "</div>" +
            '<div class="cb-reward">' + chips(item.reward) + "</div>");
        t.setAttribute("role", "status");
        root.appendChild(t);
        requestAnimationFrame(function () { t.classList.add("on"); });
        setTimeout(function () { t.classList.remove("on"); setTimeout(function () { t.remove(); }, 500); }, 4200);
    }
    function overlay(html, onClose) {
        var o = el("div", "cb-over", '<div class="in">' + html + "</div>");
        o.setAttribute("role", "dialog"); o.setAttribute("aria-modal", "true");
        root.appendChild(o);
        requestAnimationFrame(function () { o.classList.add("on"); });
        var btn = o.querySelector("[data-close]");
        if (btn) { btn.focus(); btn.addEventListener("click", function () { o.classList.remove("on"); setTimeout(function () { o.remove(); }, 400); if (onClose) onClose(); }); }
    }
    function welcome() {
        var list = state.steps.map(function (s, i) { return "<li><b>" + (i + 1) + "</b>" + esc(s.title) + "</li>"; }).join("");
        overlay(
            (FLAG ? '<img class="cb-flag" src="' + esc(FLAG) + '" alt="">' : "") +
            '<div class="cb-label">Nation founded</div>' +
            "<h2>Welcome, commander</h2>" +
            "<p>" + esc(NATION) + " is yours. Your briefing walks you through running it for real: " + state.total +
            " missions, each one done in the actual game, each one paying out. Finish them all for a bonus.</p>" +
            "<ol>" + list + "</ol>" +
            '<div class="cb-reward">' + chips(state.final_reward) + "</div>" +
            '<button type="button" class="cb-btn" data-close>Begin briefing ▸</button>',
            function () { setMin(false); renderCard(); var s = state.steps[state.current]; if (s && onPage(s) && s.kind === "visit") markVisit(s); }
        );
    }
    function graduate(reward) {
        overlay(
            (FLAG ? '<img class="cb-flag" src="' + esc(FLAG) + '" alt="">' : "") +
            '<div class="cb-label">Briefing complete</div><h2>The nation is yours</h2>' +
            "<p>You've built, traded and armed " + esc(NATION) + ". From here every decision is yours. Your graduation bonus has been paid.</p>" +
            '<div class="cb-reward">' + chips(reward) + "</div>" +
            '<button type="button" class="cb-btn" data-close>Rule your nation ▸</button>',
            function () { root.remove(); }
        );
    }

    /* ---------- flow ---------- */
    var visitTimer = 0;
    function markVisit(step) {
        clearTimeout(visitTimer);
        // Give the player a moment on the page before ticking it off.
        visitTimer = setTimeout(function () {
            api("/api/tour/visit", { step: step.key }).then(apply);
        }, 2500);
    }
    function apply(data) {
        if (!data || !data.ok) return;
        state = data;
        (data.newly_completed || []).forEach(function (n, i) { setTimeout(function () { toast(n); }, i * 600); });
        if (data.graduation_reward) { clearSpot(); card.classList.remove("on"); pill.classList.remove("on"); graduate(data.graduation_reward); return; }
        if (data.graduated || !data.active || data.current == null) { root.remove(); return; }
        renderCard();
        var step = data.steps[data.current];
        if (onPage(step) && step.kind === "visit" && !document.querySelector(".cb-over")) markVisit(step);
        if (onPage(step) && step.kind === "state" && !getMin()) {
            // Point at the exact control once the page has settled.
            setTimeout(function () { if (state.current === data.current) spotlight(step); }, 900);
        }
    }

    function start() {
        api("/api/tour/state").then(function (data) {
            if (!data || !data.ok) return;
            var params = new URLSearchParams(location.search);
            if (params.get("briefing") === "start" && !data.graduated && data.current != null) {
                state = data;
                // Drop the query param so a reload doesn't replay the welcome.
                try { params.delete("briefing"); history.replaceState(null, "", location.pathname + (params.toString() ? "?" + params : "") + location.hash); } catch (e) {}
                welcome();
                (data.newly_completed || []).forEach(toast);
                return;
            }
            apply(data);
        });
    }
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
    else start();
})();
