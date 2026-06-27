window.drawInterplanetaryRoutes = function(planets, canvasId) {
    if (!planets || planets.length < 2) return;

    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const ctx = canvas.getContext("2d");

    ctx.save();
    ctx.strokeStyle = "rgba(255, 255, 255, 0.3)";
    ctx.lineWidth = 1;
    ctx.setLineDash([5, 10]);
    ctx.shadowBlur = 8;
    ctx.shadowColor = "rgba(255, 255, 255, 0.8)";

    ctx.beginPath();
    for (let i = 0; i < planets.length; i++) {
        for (let j = i + 1; j < planets.length; j++) {
            const p1 = planets[i];
            const p2 = planets[j];
            
            // Assume planets have x and y properties for their centroids
            if (p1.x !== undefined && p1.y !== undefined && p2.x !== undefined && p2.y !== undefined) {
                ctx.moveTo(p1.x, p1.y);
                ctx.lineTo(p2.x, p2.y);
            }
        }
    }
    ctx.stroke();
    ctx.restore();
};
