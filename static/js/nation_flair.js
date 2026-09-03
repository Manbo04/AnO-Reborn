// Client-side mirror of the render_nation_name Jinja macro
// (templates/macros/game_ui.html), for Socket.IO-rendered chat messages
// where there's no server round-trip to run the macro on. Keep the two in
// sync -- same flair shape: {name_color, badge_icon, badge_name, title}.
window.renderNationFlairHTML = function (displayName, flair) {
    flair = flair || {};

    function esc(s) {
        var d = document.createElement('div');
        d.textContent = s == null ? '' : String(s);
        return d.innerHTML;
    }

    var html = '<span class="nation-name-flair"' +
        (flair.name_color ? ' style="color:' + esc(flair.name_color) + ';"' : '') + '>';
    if (flair.badge_icon) {
        html += '<span class="material-icons-outlined nation-flair-badge"' +
            (flair.badge_name ? ' title="' + esc(flair.badge_name) + '"' : '') + '>' +
            esc(flair.badge_icon) + '</span>';
    }
    html += '<span class="nation-flair-name">' + esc(displayName) + '</span>';
    if (flair.title) {
        html += '<span class="nation-flair-title">' + esc(flair.title) + '</span>';
    }
    html += '</span>';
    return html;
};
