/* ===== Affairs and Order — main script ===== */

// ---------------------------------------------------------------------------
// Utility: safe element getter (avoids crashes on pages missing elements)
// ---------------------------------------------------------------------------
function _el(id) {
    return document.getElementById(id);
}

// ---------------------------------------------------------------------------
// Generic tab system — replaces 200+ lines of copy-pasted tab functions
// ---------------------------------------------------------------------------
function activateTab(tabId, contentId, group) {
    // Deactivate all tabs and content panels in this group
    group.forEach(function(item) {
        var tab = _el(item.tab);
        var content = _el(item.content);
        if (tab) tab.classList.remove(item.tab + "click");
        if (content) content.classList.remove(item.content + "click");
    });
    // Activate the selected tab and content
    var tab = _el(tabId);
    var content = _el(contentId);
    if (tab) tab.classList.add(tabId + "click");
    if (content) content.classList.add(contentId + "click");
}

// Define tab groups
var TAB_GROUPS = {
    country: [
        { tab: "countryview", content: "view" },
        { tab: "countryrevenue", content: "revenue" },
        { tab: "countrynews", content: "news" },
        { tab: "countryactions", content: "actions" },
        { tab: "countryedit", content: "edit" }
    ],
    province: [
        { tab: "provincecity", content: "city" },
        { tab: "provinceland", content: "land" }
    ],
    city: [
        { tab: "cityelectricity", content: "electricity" },
        { tab: "cityretail", content: "retail" },
        { tab: "cityworks", content: "works" }
    ],
    land: [
        { tab: "landmilitary", content: "military" },
        { tab: "landindustry", content: "industry" },
        { tab: "landprocessing", content: "processing" }
    ],
    military: [
        { tab: "militaryland", content: "land" },
        { tab: "militaryair", content: "air" },
        { tab: "militarywater", content: "water" },
        { tab: "militaryspecial", content: "special" }
    ],
    coalition: [
        { tab: "coalitiongeneral", content: "general" },
        { tab: "coalitionjoin", content: "join" },
        { tab: "coalitionleader", content: "leader" },
        { tab: "coalitionmember", content: "member" }
    ],
    upgrades: [
        { tab: "upgradeseconomic", content: "economic" },
        { tab: "upgradesmilitary", content: "military" }
    ]
};

// Generate global tab functions from the groups above
// e.g., countryview(), countryrevenue(), militaryland(), etc.
Object.keys(TAB_GROUPS).forEach(function(groupName) {
    var group = TAB_GROUPS[groupName];
    group.forEach(function(item) {
        // Create a global function named after the tab ID
        window[item.tab] = function() {
            activateTab(item.tab, item.content, group);
        };
    });
});

// Auto-activate the first tab of each group on page load (only if elements exist)
document.addEventListener("DOMContentLoaded", function() {
    Object.keys(TAB_GROUPS).forEach(function(groupName) {
        var group = TAB_GROUPS[groupName];
        if (group.length > 0 && _el(group[0].tab)) {
            activateTab(group[0].tab, group[0].content, group);
        }
    });
});

// ---------------------------------------------------------------------------
// Navbar hamburger menu
// ---------------------------------------------------------------------------
function menubardrop() {
    var menubar = _el("menubar");
    var menudiv = _el("menubardiv");
    if (menubar) menubar.classList.toggle("menubarclick");
    if (menudiv) menudiv.classList.toggle("menubardivshow");
    var bar1 = _el("bar1");
    var bar2 = _el("bar2");
    var bar3 = _el("bar3");
    if (bar1) bar1.classList.toggle("barclick1");
    if (bar2) bar2.classList.toggle("barclick2");
    if (bar3) bar3.classList.toggle("barclick3");
    document.body.classList.toggle("body");
}

// ---------------------------------------------------------------------------
// Resource sidebar toggle
// ---------------------------------------------------------------------------
function resourcedivcontentshow() {
    var rd = _el("resourcediv");
    var rdc = _el("resourcedivcontent");
    if (rd) rd.classList.toggle("resourcedivshow");
    if (rdc) rdc.classList.toggle("resourcedivcontentshow");
    try { localStorage.setItem("resourcedivcontentshow", "true"); } catch(e) {}
}

// ---------------------------------------------------------------------------
// Country page helpers
// ---------------------------------------------------------------------------
function revenuehide() { var el = _el("countryrevenue"); if (el) el.classList.add("hidden"); }
function newshide() { var el = _el("countrynews"); if (el) el.classList.add("hidden"); }
function edithide() { var el = _el("countryedit"); if (el) el.classList.add("hidden"); }
function actionshide() { var el = _el("countryactions"); if (el) el.classList.add("hidden"); }

// Coalition helpers
function joinhide() { var el = _el("coalitionjoin"); if (el) el.classList.add("hidden"); }
function leaderhide() { var el = _el("coalitionleader"); if (el) el.classList.add("hidden"); }
function memberhide() { var el = _el("coalitionmember"); if (el) el.classList.add("hidden"); }

// ---------------------------------------------------------------------------
// Image preview for flag uploads
// ---------------------------------------------------------------------------
var imageBackground = function(event) {
    var output = document.getElementById("imageBackground");
    if (!output || !event.target.files[0]) return;
    output.src = URL.createObjectURL(event.target.files[0]);
    output.style.width = "20vw";
    output.style.height = "11.25vw";
    output.onload = function() { URL.revokeObjectURL(output.src); };
};

// ---------------------------------------------------------------------------
// Number formatting
// ---------------------------------------------------------------------------
function numberWithCommas(x) {
    return x.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

// ---------------------------------------------------------------------------
// Delete item from page and send POST request
// ---------------------------------------------------------------------------
function pop_from_page(req_path, container_id) {
    var item = document.querySelector('[data-contain="' + container_id + '"]');
    fetch(req_path, { method: "POST" });
    if (item) item.remove();
}

// ---------------------------------------------------------------------------
// Theme toggle (light/dark)
// ---------------------------------------------------------------------------
function setTheme(themeName) {
    try { localStorage.setItem("theme", themeName); } catch(e) {}
    document.documentElement.className = themeName;
}

function toggleTheme() {
    var current = "theme-light";
    try { current = localStorage.getItem("theme") || "theme-light"; } catch(e) {}
    setTheme(current === "theme-dark" ? "theme-light" : "theme-dark");
}

// Apply saved theme on load
(function() {
    var theme = "theme-light";
    try { theme = localStorage.getItem("theme") || "theme-light"; } catch(e) {}
    setTheme(theme);
    var slider = document.getElementById("slider");
    if (slider) slider.checked = (theme === "theme-dark");
})();

// ---------------------------------------------------------------------------
// War selection helpers
// ---------------------------------------------------------------------------
function assign_parameters() {
    var all_inputs = document.querySelectorAll("input[type=checkbox]");
    var next_button = document.getElementById("next_button");
    if (!next_button) return false;
    var hidden_inputs = next_button.querySelectorAll("input[type=hidden]");
    var next_hidden = 0;

    for (var i = 0; i < all_inputs.length; i++) {
        if (all_inputs[i].checked) {
            hidden_inputs[next_hidden].value = all_inputs[i].value;
            next_hidden++;
            if (next_hidden === 3) return true;
        }
    }
    return false;
}

function submit_special(e) {
    var special_unit = document.querySelector("input[name=special_unit]");
    if (!special_unit) return;
    var el11 = document.getElementById("11");
    var el10 = document.getElementById("10");
    if (el11 && el11.checked) special_unit.value = "nukes";
    else if (el10 && el10.checked) special_unit.value = "icbms";
}

function submit_next(e) {
    if (assign_parameters()) {
        e.target.parentElement.submit();
    }
}

function war_target() {
    var element = document.getElementsByName("targeted_unit")[0];
    var all_inputs = document.querySelectorAll("input[type=checkbox]");
    if (element) {
        for (var i = 0; i < all_inputs.length; i++) {
            if (all_inputs[i].checked) element.value = all_inputs[i].value;
        }
    }
}

// ---------------------------------------------------------------------------
// Flash message auto-dismiss
// ---------------------------------------------------------------------------
document.addEventListener("DOMContentLoaded", function() {
    var flashes = document.querySelectorAll(".purchasediv");
    flashes.forEach(function(flash, i) {
        // Stagger fade-out: 3s + 0.5s per message
        setTimeout(function() {
            flash.style.transition = "opacity 0.5s ease-out";
            flash.style.opacity = "0";
            setTimeout(function() { flash.remove(); }, 500);
        }, 3000 + (i * 500));
    });
});
