/**
 * Interactive AnO tutorial — progress, chapters, quizzes, widgets.
 */
(function () {
    "use strict";

    var STORAGE_KEY = "ano_tutorial_v2";
    var XP_PER_CHAPTER = 100;
    var XP_QUIZ_BONUS = 50;

    var root = document.getElementById("tutorial-interactive");
    if (!root) return;

    var constants = {};
    try {
        var raw = root.getAttribute("data-constants");
        if (raw) constants = JSON.parse(raw);
    } catch (e) {
        console.warn("Tutorial constants parse failed", e);
    }

    var chapters = Array.prototype.slice.call(
        root.querySelectorAll(".tutorial-chapter-panel")
    );
    var chapterBtns = Array.prototype.slice.call(
        root.querySelectorAll(".tutorial-chapter-btn")
    );
    var totalChapters = chapters.length;

    function loadProgress() {
        try {
            var s = localStorage.getItem(STORAGE_KEY);
            if (s) return JSON.parse(s);
        } catch (e) {}
        return {
            completed: {},
            quizzes: {},
            xp: 0,
            current: 0,
        };
    }

    function saveProgress(state) {
        try {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
        } catch (e) {}
    }

    var progress = loadProgress();

    fetch("/api/tutorial/progress", { credentials: "same-origin" })
        .then(function (res) { return res.ok ? res.json() : null; })
        .then(function (data) {
            if (!data || !data.ok || !data.chapters_claimed) return;
            data.chapters_claimed.forEach(function (idx) {
                progress.completed[idx] = true;
            });
            saveProgress(progress);
            updateStatsUI();
            unlockChapters();
        })
        .catch(function () {});

    function completedCount() {
        var n = 0;
        for (var i = 0; i < totalChapters; i++) {
            if (progress.completed[i]) n++;
        }
        return n;
    }

    function updateStatsUI() {
        var pct = totalChapters
            ? Math.round((completedCount() / totalChapters) * 100)
            : 0;
        var fill = root.querySelector(".tutorial-progress-fill");
        var pctLabel = root.querySelector("[data-tutorial-pct]");
        var xpEl = root.querySelector("[data-tutorial-xp]");
        var rankEl = root.querySelector("[data-tutorial-rank]");

        if (fill) fill.style.width = pct + "%";
        if (pctLabel) pctLabel.textContent = pct + "%";
        if (xpEl) xpEl.textContent = String(progress.xp);
        if (rankEl) rankEl.textContent = rankTitle(progress.xp);
    }

    function rankTitle(xp) {
        if (xp >= 1000) return "Grand Strategist";
        if (xp >= 750) return "War Minister";
        if (xp >= 500) return "Economist";
        if (xp >= 250) return "Governor";
        if (xp >= 100) return "Cadet";
        return "Recruit";
    }

    function setChapter(index, scroll) {
        if (index < 0 || index >= totalChapters) return;
        progress.current = index;
        saveProgress(progress);

        chapters.forEach(function (panel, i) {
            panel.classList.toggle("is-visible", i === index);
            var vid = panel.querySelector(".tutorial-lesson-video");
            if (vid && !vid.paused) {
                vid.pause();
            }
        });
        chapterBtns.forEach(function (btn, i) {
            btn.classList.toggle("is-active", i === index);
            btn.setAttribute("aria-current", i === index ? "step" : "false");
            if (i === index && btn.scrollIntoView) {
                btn.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "center" });
            }
        });

        var activePanel = chapters[index];
        if (activePanel) {
            var firstTab = activePanel.querySelector(".tutorial-tab");
            if (firstTab && !activePanel.querySelector(".tutorial-tab.is-active")) {
                activateTab(firstTab);
            }
            syncChapterControls(index);
        }

        if (scroll) {
            var stage = root.querySelector(".tutorial-stage");
            if (stage) stage.scrollIntoView({ behavior: "smooth", block: "start" });
            window.scrollTo({ top: 0, behavior: "smooth" });
        }
    }

    function syncChapterControls(chapterIndex) {
        var panel = chapters[chapterIndex];
        if (!panel) return;
        var quizKey = "ch" + chapterIndex;
        var passed = !!progress.quizzes[quizKey];
        var completeBtn = panel.querySelector("[data-chapter-complete]");
        if (completeBtn) {
            var hasQuiz = !!panel.querySelector(".tutorial-quiz");
            if (!hasQuiz || passed) {
                completeBtn.disabled = false;
                completeBtn.classList.remove("is-locked");
            } else {
                completeBtn.disabled = true;
                completeBtn.classList.add("is-locked");
            }
        }
        var howto = panel.querySelector(".tutorial-howto");
        if (howto) {
            howto.classList.toggle("is-step-quiz", !passed);
            howto.classList.toggle("is-done", passed);
        }
    }

    function injectHowTo() {
        chapters.forEach(function (panel, i) {
            if (panel.querySelector(".tutorial-howto")) return;
            var quiz = panel.querySelector(".tutorial-quiz");
            var anchor = quiz || panel.querySelector(".tutorial-chapter-body");
            if (!anchor) return;
            var howto = document.createElement("div");
            howto.className = "tutorial-howto";
            howto.innerHTML =
                '<h4 class="tutorial-howto-title"><span class="material-icons-outlined">checklist</span> What to do in this chapter</h4>' +
                '<ol class="tutorial-howto-list">' +
                "<li><span>1</span> Read the lesson (use tabs if you see them).</li>" +
                "<li><span>2</span> Open <strong>Follow along</strong> links (new tab) and try any <strong>interactive box</strong>.</li>" +
                "<li><span>3</span> Answer the quiz below, then press <strong>Check my answer</strong>.</li>" +
                "<li><span>4</span> Press <strong>Complete &amp; unlock next chapter</strong>.</li>" +
                "</ol>";
            if (quiz) {
                quiz.parentNode.insertBefore(howto, quiz);
            } else {
                anchor.insertBefore(howto, anchor.firstChild);
            }
        });
    }

    function normalizeQuizRadios(quiz, chapterIndex) {
        var questions = quiz.querySelectorAll(".tutorial-quiz-question");
        questions.forEach(function (q, qi) {
            var name = "ch" + chapterIndex + "q" + qi;
            q.querySelectorAll('input[type="radio"]').forEach(function (inp, oi) {
                inp.name = name;
                inp.value = inp.value || String.fromCharCode(97 + oi);
                inp.removeAttribute("hidden");
            });
        });
    }

    function quizAllAnswered(quiz) {
        var ok = true;
        quiz.querySelectorAll(".tutorial-quiz-question").forEach(function (q) {
            if (!q.querySelector('input[type="radio"]:checked')) ok = false;
        });
        return ok;
    }

    function unlockChapters() {
        chapterBtns.forEach(function (btn, i) {
            var unlocked = i === 0 || !!progress.completed[i - 1];
            btn.disabled = !unlocked;
            btn.classList.toggle("is-complete", !!progress.completed[i]);
            btn.setAttribute("aria-label", progress.completed[i] ? "Chapter complete" : "Chapter " + (i + 1));
        });
    }

    function showRewardToast(message, granted) {
        var toast = document.getElementById("tutorial-reward-toast");
        if (!toast) {
            toast = document.createElement("div");
            toast.id = "tutorial-reward-toast";
            toast.className = "tutorial-reward-toast";
            toast.setAttribute("role", "status");
            toast.setAttribute("aria-live", "polite");
            document.body.appendChild(toast);
        }
        var parts = [message];
        if (granted && typeof granted === "object") {
            Object.keys(granted).forEach(function (key) {
                parts.push("+" + granted[key].toLocaleString() + " " + key);
            });
        }
        toast.textContent = parts.join(" · ");
        toast.classList.add("is-show");
        setTimeout(function () {
            toast.classList.remove("is-show");
        }, 6000);
    }

    function claimTutorialReward(payload) {
        return fetch("/api/tutorial/claim", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            credentials: "same-origin",
            body: JSON.stringify(payload || {}),
        })
            .then(function (res) {
                return res.json().then(function (data) {
                    if (!res.ok || !data.ok) {
                        throw new Error((data && data.error) || "Reward claim failed");
                    }
                    return data;
                });
            })
            .then(function (data) {
                if (data.message && !data.already_claimed) {
                    showRewardToast(data.message, data.granted);
                }
                return data;
            });
    }

    function markChapterComplete(index) {
        if (progress.completed[index]) return;
        progress.completed[index] = true;
        progress.xp += XP_PER_CHAPTER;
        saveProgress(progress);
        updateStatsUI();
        unlockChapters();
        claimTutorialReward({ chapter_index: index }).catch(function (err) {
            console.warn("Tutorial chapter reward:", err.message || err);
        });
        if (completedCount() === totalChapters) {
            showGraduation();
            claimTutorialReward({ graduate: true }).catch(function (err) {
                console.warn("Tutorial graduation reward:", err.message || err);
            });
        }
    }

    function showGraduation() {
        var overlay = root.querySelector(".tutorial-complete-overlay");
        if (overlay) overlay.classList.add("is-show");
        spawnConfetti(40);
    }

    function spawnConfetti(count) {
        var colors = ["#00a7e1", "#2ecc71", "#f1c40f", "#e74c3c", "#9b59b6"];
        for (var i = 0; i < count; i++) {
            var el = document.createElement("div");
            el.className = "tutorial-confetti";
            el.style.left = Math.random() * 100 + "vw";
            el.style.top = "-10px";
            el.style.background = colors[Math.floor(Math.random() * colors.length)];
            el.style.animationDelay = Math.random() * 0.8 + "s";
            document.body.appendChild(el);
            setTimeout(function (node) {
                return function () {
                    if (node.parentNode) node.parentNode.removeChild(node);
                };
            }(el), 2600);
        }
    }

    /* Tabs */
    function activateTab(tabBtn) {
        var panel = tabBtn.closest(".tutorial-chapter-panel");
        if (!panel) return;
        var targetId = tabBtn.getAttribute("data-tab");
        panel.querySelectorAll(".tutorial-tab").forEach(function (t) {
            t.classList.toggle("is-active", t === tabBtn);
            t.setAttribute("aria-selected", t === tabBtn ? "true" : "false");
        });
        panel.querySelectorAll(".tutorial-tab-panel").forEach(function (p) {
            p.classList.toggle(
                "is-active",
                p.id === targetId
            );
        });
    }

    root.querySelectorAll(".tutorial-tab").forEach(function (tab) {
        tab.addEventListener("click", function () {
            activateTab(tab);
        });
    });

    /* Accordions */
    root.querySelectorAll(".tutorial-accordion-trigger").forEach(function (trigger) {
        trigger.addEventListener("click", function () {
            var expanded = trigger.getAttribute("aria-expanded") === "true";
            var body = trigger.parentElement.querySelector(".tutorial-accordion-body");
            trigger.setAttribute("aria-expanded", expanded ? "false" : "true");
            if (body) body.classList.toggle("is-open", !expanded);
        });
    });

    /* Tax calculator */
    var taxCalc = root.querySelector("[data-widget='tax-calc']");
    if (taxCalc) {
        var popInput = taxCalc.querySelector("[data-tax-pop]");
        var landInput = taxCalc.querySelector("[data-tax-land]");
        var cgCheck = taxCalc.querySelector("[data-tax-cg]");
        var foodCheck = taxCalc.querySelector("[data-tax-food]");
        var energyCheck = taxCalc.querySelector("[data-tax-energy]");
        var resultEl = taxCalc.querySelector("[data-tax-result]");

        var base = constants.tax_per_citizen || 0.5;
        var cgMult = constants.cg_tax_multiplier || 1.5;
        var noFood = constants.no_food_tax_multiplier || 0.7;
        var noEnergy = constants.no_energy_tax_multiplier || 0.85;
        var landMult = constants.land_tax_multiplier || 0.02;

        function updateTax() {
            var pop = parseInt(popInput.value, 10) || 0;
            var land = parseInt(landInput.value, 10) || 0;
            var hourly = pop * base;
            if (cgCheck && cgCheck.checked) hourly *= cgMult;
            if (foodCheck && !foodCheck.checked) hourly *= noFood;
            if (energyCheck && !energyCheck.checked) hourly *= noEnergy;
            hourly *= 1 + Math.min(land * landMult, 1);
            if (resultEl) {
                resultEl.innerHTML =
                    "<strong>$" +
                    formatNum(Math.round(hourly)) +
                    "</strong>/hour &nbsp;·&nbsp; <strong>$" +
                    formatNum(Math.round(hourly * 24)) +
                    "</strong>/day";
            }
        }

        [popInput, landInput, cgCheck, foodCheck, energyCheck].forEach(function (el) {
            if (el) el.addEventListener("input", updateTax);
            if (el) el.addEventListener("change", updateTax);
        });
        updateTax();
    }

    /* Province cost calculator */
    var provCalc = root.querySelector("[data-widget='province-calc']");
    if (provCalc) {
        var countInput = provCalc.querySelector("[data-prov-count]");
        var provResult = provCalc.querySelector("[data-prov-result]");
        var baseCost = constants.province_base_cost || 8000000;
        var scale = constants.province_cost_scale || 0.16;

        function updateProv() {
            var n = parseInt(countInput.value, 10) || 0;
            var cost = Math.floor(baseCost * (1 + scale * n));
            if (n === 0) cost = 2000000;
            if (n === 1) cost = 5000000;
            if (provResult) {
                var pos = n + 1;
                var suffix = "th";
                if (pos === 1) suffix = "st";
                else if (pos === 2) suffix = "nd";
                else if (pos === 3) suffix = "rd";
                provResult.innerHTML =
                    "Your <strong>" +
                    pos +
                    suffix + "</strong> province costs <strong>$" +
                    formatNum(cost) +
                    "</strong>";
            }
        }
        if (countInput) {
            countInput.addEventListener("input", updateProv);
            updateProv();
        }
    }

    /* Production chain click order */
    var chainWidget = root.querySelector("[data-widget='chain-game']");
    if (chainWidget) {
        var expected = ["bauxite", "aluminium", "components", "cg"];
        var picked = [];
        var chainMsg = chainWidget.querySelector("[data-chain-msg]");

        chainWidget.querySelectorAll(".tutorial-chain-node").forEach(function (node) {
            node.addEventListener("click", function () {
                var id = node.getAttribute("data-chain-id");
                if (!id || node.classList.contains("is-selected")) return;
                picked.push(id);
                node.classList.add("is-selected");
                if (picked.length === expected.length) {
                    var ok = picked.every(function (v, i) {
                        return v === expected[i];
                    });
                    if (chainMsg) {
                        chainMsg.textContent = ok
                            ? "Perfect! That's the industrial pipeline: mine → refine → manufacture → retail."
                            : "Not quite — try: Bauxite → Aluminium → Components → Consumer Goods.";
                        chainMsg.style.color = ok ? "#2ecc71" : "#e74c3c";
                    }
                    if (ok) picked = [];
                }
            });
        });
        var chainReset = chainWidget.querySelector("[data-chain-reset]");
        if (chainReset) {
            chainReset.addEventListener("click", function () {
                picked = [];
                chainWidget.querySelectorAll(".tutorial-chain-node").forEach(function (n) {
                    n.classList.remove("is-selected");
                });
                if (chainMsg) chainMsg.textContent = "Click each step in order from raw material to finished goods.";
            });
        }
    }

    /* Supply attack calculator */
    var supplyWidget = root.querySelector("[data-widget='supply-calc']");
    if (supplyWidget) {
        var infantry = supplyWidget.querySelector("[data-sup-infantry]");
        var tanks = supplyWidget.querySelector("[data-sup-tanks]");
        var supplyResult = supplyWidget.querySelector("[data-sup-result]");
        var minSup = constants.min_attack_supplies || 200;

        function updateSupply() {
            var inf = parseInt(infantry.value, 10) || 0;
            var tn = parseInt(tanks.value, 10) || 0;
            var cost = inf * 1 + tn * 5;
            var ok = cost >= minSup;
            if (supplyResult) {
                supplyResult.innerHTML =
                    "Attack supply cost: <strong>" +
                    cost +
                    "</strong> " +
                    (ok
                        ? "(≥ " + minSup + " — you can launch!)"
                        : "(need at least " + minSup + " supplies)");
                supplyResult.style.color = ok ? "#2ecc71" : "#e74c3c";
            }
        }
        [infantry, tanks].forEach(function (el) {
            if (el) el.addEventListener("input", updateSupply);
        });
        updateSupply();
    }

    /* Quizzes */
    function setupQuiz(panel, chapterIndex) {
        var quiz = panel.querySelector(".tutorial-quiz");
        if (!quiz) return;

        normalizeQuizRadios(quiz, chapterIndex);

        var questions = quiz.querySelectorAll(".tutorial-quiz-question");
        var submitBtn = quiz.querySelector("[data-quiz-submit]");
        var feedback = quiz.querySelector(".tutorial-quiz-feedback");
        var quizKey = "ch" + chapterIndex;

        function updateCheckButton() {
            if (!submitBtn) return;
            var ready = quizAllAnswered(quiz);
            submitBtn.disabled = !ready;
            if (ready && !progress.quizzes[quizKey]) {
                submitBtn.textContent = "Check my answer";
            }
        }

        function markPassedUI() {
            quiz.classList.add("is-done");
            if (feedback) {
                feedback.textContent =
                    "Correct! +" + XP_QUIZ_BONUS + " XP. Now press Complete below.";
                feedback.className = "tutorial-quiz-feedback is-success";
            }
            if (submitBtn) {
                submitBtn.disabled = true;
                submitBtn.textContent = "Quiz passed";
            }
            syncChapterControls(chapterIndex);
        }

        if (progress.quizzes[quizKey]) {
            markPassedUI();
            questions.forEach(function (q) {
                var correct = q.querySelector("[data-correct='true']");
                if (correct) correct.classList.add("is-correct");
            });
            return;
        }

        quiz.querySelectorAll('input[type="radio"]').forEach(function (inp) {
            inp.addEventListener("change", function () {
                var opt = inp.closest(".tutorial-quiz-option");
                var q = inp.closest(".tutorial-quiz-question");
                if (q) {
                    q.querySelectorAll(".tutorial-quiz-option").forEach(function (o) {
                        o.classList.remove("is-selected");
                    });
                }
                if (opt) opt.classList.add("is-selected");
                if (feedback && !progress.quizzes[quizKey]) {
                    feedback.textContent = "";
                    feedback.className = "tutorial-quiz-feedback";
                }
                updateCheckButton();
            });
        });

        if (submitBtn) {
            submitBtn.addEventListener("click", function () {
                if (!quizAllAnswered(quiz)) {
                    if (feedback) {
                        feedback.textContent = "Select an answer for each question first.";
                        feedback.className = "tutorial-quiz-feedback is-warn";
                    }
                    return;
                }

                var allCorrect = true;
                questions.forEach(function (q) {
                    var checked = q.querySelector('input[type="radio"]:checked');
                    var correctOpt = q.querySelector("[data-correct='true']");
                    q.querySelectorAll(".tutorial-quiz-option").forEach(function (opt) {
                        opt.classList.remove("is-correct", "is-wrong");
                    });
                    if (!checked) {
                        allCorrect = false;
                        return;
                    }
                    var chosen = checked.closest(".tutorial-quiz-option");
                    if (chosen === correctOpt) {
                        chosen.classList.add("is-correct");
                    } else {
                        allCorrect = false;
                        if (chosen) chosen.classList.add("is-wrong");
                        if (correctOpt) correctOpt.classList.add("is-correct");
                    }
                });

                if (allCorrect) {
                    progress.quizzes[quizKey] = true;
                    progress.xp += XP_QUIZ_BONUS;
                    saveProgress(progress);
                    updateStatsUI();
                    markPassedUI();
                } else {
                    if (feedback) {
                        feedback.textContent =
                            "Not quite — read the lesson again, pick a new answer, and retry.";
                        feedback.className = "tutorial-quiz-feedback is-error";
                    }
                }
            });
        }

        updateCheckButton();
    }

    injectHowTo();

    chapters.forEach(function (panel, i) {
        setupQuiz(panel, i);
        syncChapterControls(i);

        var completeBtn = panel.querySelector("[data-chapter-complete]");
        if (completeBtn) {
            completeBtn.addEventListener("click", function () {
                var quiz = panel.querySelector(".tutorial-quiz");
                var quizKey = "ch" + i;
                if (quiz && !progress.quizzes[quizKey]) {
                    var fb = quiz.querySelector(".tutorial-quiz-feedback");
                    if (fb) {
                        fb.textContent = "Pass the quiz first to earn XP and unlock the next chapter!";
                        fb.style.color = "#f39c12";
                    }
                    return;
                }
                markChapterComplete(i);
                if (i + 1 < totalChapters) {
                    setChapter(i + 1, true);
                } else {
                    showGraduation();
                }
            });
        }

        var skipBtn = panel.querySelector("[data-chapter-skip]");
        if (skipBtn) {
            skipBtn.addEventListener("click", function () {
                markChapterComplete(i);
                progress.xp = Math.max(0, progress.xp - 25);
                saveProgress(progress);
                updateStatsUI();
                if (i + 1 < totalChapters) setChapter(i + 1, true);
            });
        }
    });

    chapterBtns.forEach(function (btn, i) {
        btn.addEventListener("click", function () {
            if (!btn.disabled) setChapter(i, true);
        });
    });

    var introOverlay = document.getElementById("tutorial-intro-overlay");
    var introDismiss = document.getElementById("tutorial-intro-dismiss");
    var INTRO_KEY = "ano_tutorial_intro_seen";
    if (introOverlay && !localStorage.getItem(INTRO_KEY)) {
        introOverlay.classList.add("is-show");
        introOverlay.setAttribute("aria-hidden", "false");
    }
    if (introDismiss && introOverlay) {
        introDismiss.addEventListener("click", function () {
            introOverlay.classList.remove("is-show");
            introOverlay.setAttribute("aria-hidden", "true");
            try {
                localStorage.setItem(INTRO_KEY, "1");
            } catch (e) {}
        });
    }

    var resetBtn = root.querySelector("[data-tutorial-reset]");
    if (resetBtn) {
        resetBtn.addEventListener("click", function () {
            if (
                confirm(
                    "Reset all tutorial progress? This clears XP, completed chapters, and quiz scores."
                )
            ) {
                progress = {
                    completed: {},
                    quizzes: {},
                    xp: 0,
                    current: 0,
                };
                saveProgress(progress);
                location.reload();
            }
        });
    }

    var closeGrad = root.querySelector("[data-close-graduation]");
    if (closeGrad) {
        closeGrad.addEventListener("click", function () {
            var overlay = root.querySelector(".tutorial-complete-overlay");
            if (overlay) overlay.classList.remove("is-show");
        });
    }

    function formatNum(n) {
        return n.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
    }

    root.querySelectorAll(".tutorial-follow-btn").forEach(function (link) {
        link.addEventListener("click", function () {
            try {
                sessionStorage.setItem(
                    "tutorialReturn",
                    window.location.pathname + window.location.search
                );
            } catch (e) { /* ignore */ }
        });
    });

    unlockChapters();
    updateStatsUI();
    setChapter(progress.current || 0, false);
})();


class TutorialSpotlight {
    constructor() {
        this.overlay = document.createElement('div');
        this.overlay.id = 'tutorial-spotlight-overlay';
        document.body.appendChild(this.overlay);
        
        // Prevent clicks on the dark overlay from reaching other UI elements
        this.overlay.addEventListener('click', (e) => {
            e.stopPropagation();
            e.preventDefault();
        });

        // Recalculate on resize to keep spotlight over the element
        window.addEventListener('resize', () => {
            if (this.currentTarget) {
                this.highlight(this.currentTarget);
            }
        });
    }

    highlight(targetSelectorOrElement, padding = 5) {
        let el = targetSelectorOrElement;
        if (typeof targetSelectorOrElement === 'string') {
            el = document.querySelector(targetSelectorOrElement);
        }

        if (!el) {
            this.clear();
            return;
        }

        this.currentTarget = el;
        const rect = el.getBoundingClientRect();
        
        // Ensure bounds don't crash the polygon
        const top = Math.max(0, rect.top - padding);
        const left = Math.max(0, rect.left - padding);
        const right = Math.min(window.innerWidth, rect.right + padding);
        const bottom = Math.min(window.innerHeight, rect.bottom + padding);

        // Clip-path polygon with a hole.
        // Outer box goes clockwise, inner box (the hole) goes counter-clockwise.
        const polygon = `polygon(
            0% 0%, 100% 0%, 100% 100%, 0% 100%, 0% 0%, 
            ${left}px ${top}px, 
            ${left}px ${bottom}px, 
            ${right}px ${bottom}px, 
            ${right}px ${top}px, 
            ${left}px ${top}px
        )`;

        this.overlay.style.clipPath = polygon;
        this.overlay.style.webkitClipPath = polygon; // Safari support
        this.overlay.classList.add('active');
        
        // Scroll the element into view smoothly if not visible
        if (rect.top < 0 || rect.bottom > window.innerHeight) {
            el.scrollIntoView({ behavior: 'smooth', block: 'center' });
            setTimeout(() => this.highlight(el, padding), 300);
        }
    }

    clear() {
        this.currentTarget = null;
        this.overlay.classList.remove('active');
        this.overlay.style.clipPath = 'none';
        this.overlay.style.webkitClipPath = 'none';
    }
}
window.TutorialSpotlight = TutorialSpotlight;

