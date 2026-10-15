(function () {
    "use strict";
    const viewport = document.getElementById("viewport");
    const canvas = document.getElementById("map-canvas");
    const status = document.getElementById("map-status");
    if (!viewport || !canvas || !status) return;
    const ctx = canvas.getContext("2d", { alpha: false });
    if (!ctx) {
        status.textContent = "This browser could not start the map renderer.";
        return;
    }

    const HEX_SIZE = 50;
    const HEX_SPACING = 1.03;
    const MIN_SCALE = 0.06;
    const MAX_SCALE = 3;
    const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
    const imageCache = new Map();
    let width = 0;
    let height = 0;
    let scale = 1;
    let panX = 0;
    let panY = 0;
    let planets = [];
    let provinces = [];
    let stars = [];
    let pointerStart = null;
    let dragging = false;
    let renderQueued = false;

    function clamp(value, min, max) {
        return Math.max(min, Math.min(max, value));
    }

    function pointForHex(q, r) {
        return {
            x: HEX_SIZE * Math.sqrt(3) * (q + r / 2) * HEX_SPACING,
            y: HEX_SIZE * 1.5 * r * HEX_SPACING
        };
    }

    function pointForPlanet(planet) {
        return pointForHex(Number(planet.x) || 0, Number(planet.y) || 0);
    }

    function setStatus(message, isError) {
        status.textContent = message;
        status.hidden = !message;
        status.classList.toggle("map-status-error", Boolean(isError));
    }

    function makeStars() {
        let seed = 16411;
        function random() {
            seed = (seed * 16807) % 2147483647;
            return (seed - 1) / 2147483646;
        }
        stars = [];
        const count = Math.min(170, Math.round(width * height / 9000));
        for (let i = 0; i < count; i++) {
            stars.push({
                x: random() * width,
                y: random() * height,
                radius: 0.4 + random() * 1.1,
                alpha: 0.14 + random() * 0.5
            });
        }
    }

    function queueRender() {
        if (renderQueued) return;
        renderQueued = true;
        requestAnimationFrame(function () {
            renderQueued = false;
            render();
        });
    }

    function resizeCanvas() {
        const rect = viewport.getBoundingClientRect();
        width = Math.max(1, rect.width);
        height = Math.max(1, rect.height);
        canvas.width = Math.round(width * dpr);
        canvas.height = Math.round(height * dpr);
        canvas.style.width = width + "px";
        canvas.style.height = height + "px";
        makeStars();
        queueRender();
    }

    function getImage(type) {
        if (!imageCache.has(type)) {
            const image = new Image();
            const entry = { image: image, ready: false };
            image.onload = function () {
                entry.ready = true;
                queueRender();
            };
            image.onerror = function () {
                entry.failed = true;
                queueRender();
            };
            image.src = "/static/img/planet_" + encodeURIComponent(type) + ".jpg";
            imageCache.set(type, entry);
        }
        return imageCache.get(type);
    }

    function drawBackground() {
        ctx.fillStyle = "#070b14";
        ctx.fillRect(0, 0, width, height);
        const glow = ctx.createRadialGradient(width * 0.5, height * 0.45, 0, width * 0.5, height * 0.45, Math.max(width, height) * 0.78);
        glow.addColorStop(0, "rgba(20,42,75,0.58)");
        glow.addColorStop(1, "rgba(7,11,20,0)");
        ctx.fillStyle = glow;
        ctx.fillRect(0, 0, width, height);
        for (const star of stars) {
            ctx.globalAlpha = star.alpha;
            ctx.fillStyle = "#c9e5ff";
            ctx.beginPath();
            ctx.arc(star.x, star.y, star.radius, 0, Math.PI * 2);
            ctx.fill();
        }
        ctx.globalAlpha = 1;
    }

    function visibleBounds(centerX, centerY) {
        return {
            left: (-centerX - panX) / scale,
            right: (width - centerX - panX) / scale,
            top: (-centerY - panY) / scale,
            bottom: (height - centerY - panY) / scale
        };
    }

    function drawPlanetRing(x, y, radius, alpha) {
        ctx.save();
        ctx.translate(x, y);
        ctx.rotate(-0.24);
        ctx.scale(1, 0.27);
        ctx.beginPath();
        ctx.ellipse(0, 0, radius * 1.34, radius * 1.34, 0, 0, Math.PI * 2);
        ctx.strokeStyle = "rgba(177,214,255," + alpha + ")";
        ctx.lineWidth = Math.max(2 / scale, radius * 0.055);
        ctx.stroke();
        ctx.restore();
    }

    function drawPlanet(planet, bounds) {
        const point = pointForPlanet(planet);
        const radius = Math.max(24, Number(planet.radius) || 320);
        if (point.x + radius < bounds.left || point.x - radius > bounds.right ||
            point.y + radius < bounds.top || point.y - radius > bounds.bottom) return;

        const isHome = Boolean(planet.is_home);
        if (planet.type === "ringed") drawPlanetRing(point.x, point.y, radius, 0.42);

        ctx.save();
        ctx.beginPath();
        ctx.arc(point.x, point.y, radius, 0, Math.PI * 2);
        ctx.clip();
        const texture = getImage(planet.type);
        if (texture.ready) {
            ctx.drawImage(texture.image, point.x - radius, point.y - radius, radius * 2, radius * 2);
        } else {
            const fallback = ctx.createRadialGradient(
                point.x - radius * 0.32, point.y - radius * 0.4, radius * 0.05,
                point.x, point.y, radius
            );
            fallback.addColorStop(0, "#5ab7c5");
            fallback.addColorStop(0.65, "#1d4d75");
            fallback.addColorStop(1, "#09101d");
            ctx.fillStyle = fallback;
            ctx.fillRect(point.x - radius, point.y - radius, radius * 2, radius * 2);
        }

        const shade = ctx.createRadialGradient(
            point.x - radius * 0.42, point.y - radius * 0.42, radius * 0.05,
            point.x + radius * 0.14, point.y + radius * 0.12, radius * 1.12
        );
        shade.addColorStop(0, "rgba(255,255,255,0.12)");
        shade.addColorStop(0.58, "rgba(5,10,20,0.02)");
        shade.addColorStop(1, "rgba(0,3,12,0.76)");
        ctx.fillStyle = shade;
        ctx.fillRect(point.x - radius, point.y - radius, radius * 2, radius * 2);
        ctx.restore();

        ctx.beginPath();
        ctx.arc(point.x, point.y, radius - 1, 0, Math.PI * 2);
        ctx.strokeStyle = isHome ? "rgba(133,224,255,0.95)" : "rgba(164,204,235,0.5)";
        ctx.lineWidth = (isHome ? 3 : 1.5) / scale;
        ctx.stroke();

        const atmosphere = ctx.createRadialGradient(point.x, point.y, radius * 0.9, point.x, point.y, radius * 1.16);
        atmosphere.addColorStop(0, isHome ? "rgba(69,198,255,0.22)" : "rgba(69,150,210,0.12)");
        atmosphere.addColorStop(1, "rgba(69,150,210,0)");
        ctx.fillStyle = atmosphere;
        ctx.beginPath();
        ctx.arc(point.x, point.y, radius * 1.16, 0, Math.PI * 2);
        ctx.fill();

        if (planet.type === "ringed") drawPlanetRing(point.x, point.y, radius, 0.78);
        if (scale >= 0.32 || isHome) {
            const label = String(planet.name || "Unknown nation");
            const fontSize = (isHome ? 15 : 12) / scale;
            ctx.font = "600 " + fontSize + "px Inter, system-ui, sans-serif";
            ctx.textAlign = "center";
            ctx.textBaseline = "middle";
            const labelY = point.y + radius + 24 / scale;
            const textWidth = ctx.measureText(label).width;
            const padX = 12 / scale;
            const padY = 7 / scale;
            ctx.fillStyle = isHome ? "rgba(5,17,29,0.9)" : "rgba(5,10,18,0.82)";
            ctx.fillRect(point.x - textWidth / 2 - padX, labelY - fontSize / 2 - padY,
                textWidth + padX * 2, fontSize + padY * 2);
            ctx.fillStyle = isHome ? "#b9edff" : "#d3dfed";
            ctx.fillText(label, point.x, labelY);
        }
    }

    function drawHex(q, r) {
        const point = pointForHex(q, r);
        const size = HEX_SIZE * 0.82;
        ctx.beginPath();
        for (let i = 0; i < 6; i++) {
            const angle = Math.PI / 3 * i - Math.PI / 6;
            const x = point.x + size * Math.cos(angle);
            const y = point.y + size * Math.sin(angle);
            if (i === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
        }
        ctx.closePath();
        ctx.fillStyle = "rgba(10,23,38,0.78)";
        ctx.fill();
        ctx.lineWidth = 1.5 / scale;
        ctx.strokeStyle = "rgba(88,196,245,0.86)";
        ctx.stroke();

        if (scale >= 0.72) {
            const province = provinces.find(function (item) {
                return Number(item.x) === q && Number(item.y) === r;
            });
            if (province) {
                const name = String(province.name || "Province");
                ctx.font = "600 " + (10 / scale) + "px Inter, system-ui, sans-serif";
                ctx.textAlign = "center";
                ctx.textBaseline = "middle";
                ctx.fillStyle = "#f1f7ff";
                const maxWidth = 64 / scale;
                let label = name;
                while (ctx.measureText(label).width > maxWidth && label.length > 4) {
                    label = label.slice(0, -2) + "…";
                }
                ctx.fillText(label, point.x, point.y);
            }
        }
        return point;
    }

    function drawProvince(province, bounds) {
        const q = Number(province.x);
        const r = Number(province.y);
        if (!Number.isFinite(q) || !Number.isFinite(r)) return;
        const point = pointForHex(q, r);
        const margin = HEX_SIZE * 1.1;
        if (point.x < bounds.left - margin || point.x > bounds.right + margin ||
            point.y < bounds.top - margin || point.y > bounds.bottom + margin) return;
        drawHex(q, r);
    }

    function render() {
        if (!width || !height) return;
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        drawBackground();
        const centerX = width / 2;
        const centerY = height / 2;
        const bounds = visibleBounds(centerX, centerY);
        ctx.save();
        ctx.translate(centerX + panX, centerY + panY);
        ctx.scale(scale, scale);
        for (const planet of planets) drawPlanet(planet, bounds);
        for (const province of provinces) drawProvince(province, bounds);
        ctx.restore();
    }

    function setViewOnHome() {
        const target = planets.find(function (planet) { return planet.is_home; }) || planets[0];
        if (!target) {
            scale = 1;
            panX = 0;
            panY = 0;
            queueRender();
            return;
        }
        const point = pointForPlanet(target);
        const radius = Math.max(24, Number(target.radius) || 320);
        const usableWidth = Math.max(240, width - 72);
        const usableHeight = Math.max(240, height - 190);
        scale = clamp(Math.min(usableWidth, usableHeight) / (radius * 2 + 120), 0.35, 1.2);
        panX = -point.x * scale;
        panY = -point.y * scale;
        queueRender();
    }

    function zoomAt(x, y, factor) {
        const worldX = (x - width / 2 - panX) / scale;
        const worldY = (y - height / 2 - panY) / scale;
        const nextScale = clamp(scale * factor, MIN_SCALE, MAX_SCALE);
        panX = x - width / 2 - worldX * nextScale;
        panY = y - height / 2 - worldY * nextScale;
        scale = nextScale;
        queueRender();
    }

    function provinceAt(screenX, screenY) {
        const worldX = (screenX - width / 2 - panX) / scale;
        const worldY = (screenY - height / 2 - panY) / scale;
        let closest = null;
        let closestDistance = 56;
        for (const province of provinces) {
            const point = pointForHex(Number(province.x), Number(province.y));
            const distance = Math.hypot(point.x - worldX, point.y - worldY);
            if (distance < closestDistance) {
                closest = province;
                closestDistance = distance;
            }
        }
        return closest;
    }

    canvas.addEventListener("pointerdown", function (event) {
        if (event.button !== undefined && event.button !== 0) return;
        pointerStart = { x: event.clientX, y: event.clientY, panX: panX, panY: panY };
        dragging = false;
        try { canvas.setPointerCapture(event.pointerId); } catch (_) {}
    });

    canvas.addEventListener("pointermove", function (event) {
        if (!pointerStart) return;
        const dx = event.clientX - pointerStart.x;
        const dy = event.clientY - pointerStart.y;
        if (Math.abs(dx) + Math.abs(dy) > 4) dragging = true;
        if (dragging) {
            panX = pointerStart.panX + dx;
            panY = pointerStart.panY + dy;
            queueRender();
        }
    });

    canvas.addEventListener("pointerup", function (event) {
        if (!pointerStart) return;
        if (!dragging) {
            const rect = canvas.getBoundingClientRect();
            const province = provinceAt(event.clientX - rect.left, event.clientY - rect.top);
            if (province && province.id) window.location.href = "/province/" + encodeURIComponent(province.id);
        }
        pointerStart = null;
        dragging = false;
    });

    canvas.addEventListener("pointercancel", function () {
        pointerStart = null;
        dragging = false;
    });

    canvas.addEventListener("wheel", function (event) {
        event.preventDefault();
        const rect = canvas.getBoundingClientRect();
        zoomAt(event.clientX - rect.left, event.clientY - rect.top, Math.exp(-event.deltaY * 0.001));
    }, { passive: false });

    window.zoom = function (amount) {
        zoomAt(width / 2, height / 2, amount > 0 ? 1.25 : 0.8);
    };
    window.resetView = setViewOnHome;
    window.addEventListener("resize", resizeCanvas);
    resizeCanvas();

    fetch("/api/province_map/nodes", { credentials: "same-origin" })
        .then(function (response) {
            if (!response.ok) throw new Error("Map request failed with status " + response.status);
            return response.json();
        })
        .then(function (data) {
            if (data.status !== "success") throw new Error("The map service returned an error.");
            provinces = Array.isArray(data.provinces) ? data.provinces : [];
            planets = Array.isArray(data.planets) ? data.planets : [];
            if (!provinces.length && !planets.length) {
                setStatus("No province worlds are available yet. Map locations will appear once provinces have coordinates.", false);
                return;
            }
            setStatus("", false);
            setViewOnHome();
            queueRender();
        })
        .catch(function (error) {
            console.error("Unable to load province map:", error);
            setStatus("The province map could not load. Refresh the page to try again.", true);
        });
})();
