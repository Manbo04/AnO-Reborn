//ADD STYLES
addStyles()

function addStyles() {
    let styles = `
    @keyframes floatUp {
        0% { opacity: 0; transform: translateY(100px); }
        100% { opacity: 1; transform: translateY(0); }
    }
    @keyframes floatDown {
        0% { opacity: 0; transform: translateY(-100px); }
        100% { opacity: 1; transform: translateY(0); }
    }
    @keyframes floatLeft {
        0% { opacity: 0; transform: translateX(100px); }
        100% { opacity: 1; transform: translateX(0); }
    }
    @keyframes floatRight {
        0% { opacity: 0; transform: translateX(-100px); }
        100% { opacity: 1; transform: translateX(0); }
    }
    @keyframes still {
        0% { opacity: 0; }
        100% { opacity: 1; }
    }

    .animate {
        opacity: 0;
        pointer-events: none;
    }
    .animateShow {
        opacity: 1;
        pointer-events: all;
        animation-fill-mode: forwards;
    }
    `

    var styleSheet = document.createElement("style")
    styleSheet.innerHTML = styles
    document.head.appendChild(styleSheet)
}

//ANIMATIONS using IntersectionObserver
// NOTE (player-reported 2026-08-30, "lower part isn't loading"): with a
// shrunk rootMargin (-100px on the bottom edge) and a 0.1 threshold, the
// detection band this observer watches is fairly thin. A single large,
// fast scroll jump (scrollbar drag, End key, a fast trackpad fling, or a
// layout jump right after images/fonts finish loading) can move a whole
// section from "below the viewport" to "above the viewport" between two
// sampled frames without ever registering 10% overlap inside that thin
// band -- IntersectionObserver then never reports it as intersecting, so
// it never gets .animateShow and stays permanently opacity:0/pointer-events:
// none (looks exactly like the section "never loaded"). Widening the band
// with a generous positive rootMargin + threshold 0 makes it far harder to
// jump across in one frame, and the scroll/resize sweep below is a cheap
// safety net that force-reveals anything still stuck.
const observerOptions = {
    root: null,
    rootMargin: '150px 0px 150px 0px',
    threshold: 0
};

function revealItem(item) {
    if (item.classList.contains("animateShow")) return;

    if (!item.dataset.time) {
        item.dataset.time = "0.5";
    }
    item.style.animationDuration = item.dataset.time + "s";

    item.classList.add("animateShow");

    if (item.classList.contains("floatUp")) {
        item.style.animationName = "floatUp";
    } else if (item.classList.contains("floatDown")) {
        item.style.animationName = "floatDown";
    } else if (item.classList.contains("floatLeft")) {
        item.style.animationName = "floatLeft";
    } else if (item.classList.contains("floatRight")) {
        item.style.animationName = "floatRight";
    } else {
        item.style.animationName = "still";
    }
}

const observer = new IntersectionObserver((entries, observer) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            revealItem(entry.target);
            // Stop observing once animated in
            observer.unobserve(entry.target);
        }
    });
}, observerOptions);

// Safety net: on scroll/resize, catch any .animate item the observer missed
// (e.g. a fast scroll that jumped straight past its detection band) by
// force-revealing anything that's already on screen or already scrolled by.
let sweepScheduled = false;
function sweepMissedAnimateItems() {
    sweepScheduled = false;
    document.querySelectorAll(".animate:not(.animateShow)").forEach(item => {
        const rect = item.getBoundingClientRect();
        if (rect.top < window.innerHeight + 150 && rect.bottom > -150) {
            revealItem(item);
            observer.unobserve(item);
        }
    });
}
function scheduleSweep() {
    if (sweepScheduled) return;
    sweepScheduled = true;
    requestAnimationFrame(sweepMissedAnimateItems);
}
window.addEventListener("scroll", scheduleSweep, { passive: true });
window.addEventListener("resize", scheduleSweep);

function initAnimateObservers() {
    document.querySelectorAll(".animate").forEach(item => {
        observer.observe(item);
    });
    // Catch anything already in view before the first scroll/resize fires.
    scheduleSweep();
}

// "load" can in rare cases (script served from cache, page restored from
// bfcache-adjacent states) fire before this listener attaches -- guard with
// readyState so the reveal logic isn't skipped entirely in that case.
if (document.readyState === "complete") {
    initAnimateObservers();
} else {
    window.addEventListener("load", initAnimateObservers);
}
