(function () {
    var STORAGE_PREFIX = "ano_tutorial_prompt_snooze_";
    var SNOOZE_MS = 24 * 60 * 60 * 1000;

    function snoozeKey(userId) {
        return STORAGE_PREFIX + String(userId);
    }

    function isSnoozed(userId) {
        try {
            var raw = localStorage.getItem(snoozeKey(userId));
            if (!raw) return false;
            return Date.now() < Number(raw);
        } catch (err) {
            return false;
        }
    }

    function snooze(userId) {
        try {
            localStorage.setItem(snoozeKey(userId), String(Date.now() + SNOOZE_MS));
        } catch (err) {
            /* ignore quota errors */
        }
    }

    function hideModal(modal) {
        modal.setAttribute("aria-hidden", "true");
        modal.hidden = true;
        document.body.classList.remove("onboarding-tutorial-open");
    }

    function showModal(modal) {
        modal.removeAttribute("hidden");
        modal.setAttribute("aria-hidden", "false");
        document.body.classList.add("onboarding-tutorial-open");
        var cta = modal.querySelector(".onboarding-tutorial-cta");
        if (cta) cta.focus();
    }

    function initTutorialPopup() {
        var modal = document.getElementById("onboarding-tutorial-popup");
        if (!modal) return;

        var userId = modal.getAttribute("data-user-id");
        var path = window.location.pathname || "";
        if (path === "/tutorial" || path.indexOf("/tutorial/") === 0) return;
        if (userId && isSnoozed(userId)) return;

        showModal(modal);

        modal.querySelectorAll("[data-tutorial-popup-dismiss]").forEach(function (el) {
            el.addEventListener("click", function () {
                if (userId) snooze(userId);
                hideModal(modal);
            });
        });

        var later = modal.querySelector("[data-tutorial-popup-later]");
        if (later) {
            later.addEventListener("click", function () {
                if (userId) snooze(userId);
                hideModal(modal);
            });
        }

        document.addEventListener("keydown", function (ev) {
            if (ev.key === "Escape" && !modal.hidden) {
                if (userId) snooze(userId);
                hideModal(modal);
            }
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initTutorialPopup);
    } else {
        initTutorialPopup();
    }
})();
