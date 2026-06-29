//CONSTANTS
let animateItems = document.querySelectorAll(".animate")

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
const observerOptions = {
    root: null,
    rootMargin: '0px 0px -100px 0px',
    threshold: 0.1
};

const observer = new IntersectionObserver((entries, observer) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            let item = entry.target;
            
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
            
            // Stop observing once animated in
            observer.unobserve(item);
        }
    });
}, observerOptions);

window.addEventListener("load", () => {
    animateItems.forEach(item => {
        observer.observe(item);
    });
});
