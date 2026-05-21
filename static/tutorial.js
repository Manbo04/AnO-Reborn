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
        });
        chapterBtns.forEach(function (btn, i) {
            btn.classList.toggle("is-active", i === index);
            btn.setAttribute("aria-current", i === index ? "step" : "false");
        });

        var activePanel = chapters[index];
        if (activePanel) {
            var firstTab = activePanel.querySelector(".tutorial-tab");
            if (firstTab && !activePanel.querySelector(".tutorial-tab.is-active")) {
                activateTab(firstTab);
            }
        }

        if (scroll) {
            var main = root.querySelector(".tutorial-main-panel");
            if (main) main.scrollIntoView({ behavior: "smooth", block: "start" });
        }
    }

    function unlockChapters() {
        chapterBtns.forEach(function (btn, i) {
            var unlocked = i === 0 || !!progress.completed[i - 1];
            btn.disabled = !unlocked;
            btn.classList.toggle("is-complete", !!progress.completed[i]);
            var icon = btn.querySelector(".tutorial-chapter-icon");
            if (icon) {
                icon.textContent = progress.completed[i] ? "check_circle" : "radio_button_unchecked";
            }
        });
    }

    function markChapterComplete(index) {
        if (progress.completed[index]) return;
        progress.completed[index] = true;
        progress.xp += XP_PER_CHAPTER;
        saveProgress(progress);
        updateStatsUI();
        unlockChapters();
        if (completedCount() === totalChapters) {
            showGraduation();
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
            if (provResult) {
                provResult.innerHTML =
                    "Your <strong>" +
                    (n + 1) +
                    "th</strong> province costs <strong>$" +
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

    /* Flip cards — track reveals */
    root.querySelectorAll(".tutorial-flip-card").forEach(function (card) {
        card.addEventListener("click", function () {
            card.classList.toggle("is-flipped");
        });
    });

    /* Quizzes */
    function setupQuiz(panel, chapterIndex) {
        var quiz = panel.querySelector(".tutorial-quiz");
        if (!quiz) return;

        var questions = quiz.querySelectorAll(".tutorial-quiz-question");
        var submitBtn = quiz.querySelector("[data-quiz-submit]");
        var feedback = quiz.querySelector(".tutorial-quiz-feedback");
        var quizKey = "ch" + chapterIndex;

        if (progress.quizzes[quizKey]) {
            quiz.classList.add("is-done");
            if (feedback) {
                feedback.textContent = "Quiz passed! +" + XP_QUIZ_BONUS + " XP earned.";
                feedback.style.color = "#2ecc71";
            }
            questions.forEach(function (q) {
                var correct = q.querySelector("[data-correct='true']");
                if (correct) correct.classList.add("is-correct");
            });
            return;
        }

        if (submitBtn) {
            submitBtn.addEventListener("click", function () {
                var allCorrect = true;
                questions.forEach(function (q) {
                    var selected = q.querySelector(
                        ".tutorial-quiz-option.is-selected"
                    );
                    var correctOpt = q.querySelector("[data-correct='true']");
                    q.querySelectorAll(".tutorial-quiz-option").forEach(function (opt) {
                        opt.classList.remove("is-correct", "is-wrong");
                    });
                    if (!selected) {
                        allCorrect = false;
                        return;
                    }
                    if (selected === correctOpt) {
                        selected.classList.add("is-correct");
                    } else {
                        allCorrect = false;
                        selected.classList.add("is-wrong");
                        if (correctOpt) correctOpt.classList.add("is-correct");
                    }
                });

                if (allCorrect) {
                    progress.quizzes[quizKey] = true;
                    progress.xp += XP_QUIZ_BONUS;
                    saveProgress(progress);
                    updateStatsUI();
                    if (feedback) {
                        feedback.textContent =
                            "Excellent! +" + XP_QUIZ_BONUS + " XP. You can complete this chapter.";
                        feedback.style.color = "#2ecc71";
                    }
                    quiz.classList.add("is-done");
                } else {
                    if (feedback) {
                        feedback.textContent =
                            "Some answers were wrong — review the lesson and try again!";
                        feedback.style.color = "#e74c3c";
                    }
                }
            });
        }

        quiz.querySelectorAll(".tutorial-quiz-option").forEach(function (opt) {
            opt.addEventListener("click", function () {
                var q = opt.closest(".tutorial-quiz-question");
                q.querySelectorAll(".tutorial-quiz-option").forEach(function (o) {
                    o.classList.remove("is-selected");
                });
                opt.classList.add("is-selected");
            });
        });
    }

    chapters.forEach(function (panel, i) {
        setupQuiz(panel, i);

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

    var prevBtn = root.querySelector("[data-nav-prev]");
    var nextBtn = root.querySelector("[data-nav-next]");
    if (prevBtn) {
        prevBtn.addEventListener("click", function () {
            if (progress.current > 0) setChapter(progress.current - 1, true);
        });
    }
    if (nextBtn) {
        nextBtn.addEventListener("click", function () {
            var quizKey = "ch" + progress.current;
            var panel = chapters[progress.current];
            var quiz = panel && panel.querySelector(".tutorial-quiz");
            if (quiz && !progress.quizzes[quizKey]) {
                var fb = quiz.querySelector(".tutorial-quiz-feedback");
                if (fb) {
                    fb.textContent = "Complete the quiz or use 'Mark complete' to continue.";
                    fb.style.color = "#f39c12";
                }
                return;
            }
            markChapterComplete(progress.current);
            if (progress.current + 1 < totalChapters) {
                setChapter(progress.current + 1, true);
            }
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

    unlockChapters();
    updateStatsUI();
    setChapter(progress.current || 0, false);
})();
