(function () {
    'use strict';

    function parseDemographicsData() {
        var el = document.getElementById('province-demographics-data');
        if (!el || !el.textContent) return null;
        try {
            return JSON.parse(el.textContent);
        } catch (e) {
            return null;
        }
    }

    function formatWeight(value) {
        if (value >= 1000000000) return (value / 1000000000).toFixed(1) + ' Mt';
        if (value >= 1000000) return (value / 1000000).toFixed(1) + ' kt';
        if (value >= 1000) return (value / 1000).toFixed(1) + ' t';
        return value.toFixed(0) + ' kg';
    }

    function renderChart(data) {
        var canvas = document.getElementById('provinceDemographicsChart');
        if (!canvas || !data) return false;

        var wrapper = canvas.closest('.chart-wrapper');
        if (wrapper) {
            wrapper.classList.remove('chart-wrapper--empty');
        }

        var totalPop = data.population > 0 ? data.population : 1;
        var childrenPct = (data.pop_children / totalPop) * 100;
        var workingPct = (data.pop_working / totalPop) * 100;
        var elderlyPct = (data.pop_elderly / totalPop) * 100;

        if (
            data.pop_children === 0 &&
            data.pop_working === 0 &&
            data.pop_elderly === 0 &&
            wrapper
        ) {
            wrapper.classList.add('chart-wrapper--empty');
        }

        if (typeof Chart !== 'undefined' && Chart.getChart) {
            var existing = Chart.getChart(canvas);
            if (existing) existing.destroy();
        }

        new Chart(canvas, {
            type: 'radar',
            data: {
                labels: ['Children', 'Working Age', 'Elderly'],
                datasets: [{
                    label: data.name + ' (% of Population)',
                    data: [childrenPct, workingPct, elderlyPct],
                    backgroundColor: 'rgba(94, 89, 255, 0.15)',
                    borderColor: 'rgba(94, 89, 255, 1)',
                    borderWidth: 2.5,
                    pointBackgroundColor: 'rgba(94, 89, 255, 1)',
                    pointBorderColor: '#fff',
                    pointBorderWidth: 1.5,
                    pointRadius: 4,
                    pointHoverBackgroundColor: '#fff',
                    pointHoverBorderColor: 'rgba(94, 89, 255, 1)',
                    pointHoverRadius: 6,
                    tension: 0.4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: { duration: 800, easing: 'easeInOutQuart' },
                scales: {
                    r: {
                        beginAtZero: true,
                        max: 100,
                        ticks: {
                            stepSize: 25,
                            callback: function (value) { return value + '%'; },
                            font: { size: 11 }
                        },
                        grid: { color: 'rgba(200, 200, 200, 0.1)' },
                        angleLines: { color: 'rgba(200, 200, 200, 0.15)' }
                    }
                },
                plugins: {
                    legend: { display: false },
                    title: {
                        display: true,
                        text: 'Demographic Structure: ' + data.name,
                        font: { size: 12, weight: 'bold' },
                        padding: 8
                    },
                    tooltip: {
                        backgroundColor: 'rgba(0, 0, 0, 0.85)',
                        padding: 12,
                        cornerRadius: 8,
                        titleFont: { size: 12, weight: 'bold' },
                        bodyFont: { size: 11 },
                        borderColor: 'rgba(255, 255, 255, 0.3)',
                        borderWidth: 1,
                        callbacks: {
                            label: function (context) {
                                var label = context.label || '';
                                var pct = context.parsed.r.toFixed(1);
                                var counts = {
                                    'Children': data.pop_children,
                                    'Working Age': data.pop_working,
                                    'Elderly': data.pop_elderly
                                };
                                var count = counts[label] || 0;
                                return label + ': ' + pct + '% (' + formatWeight(count) + ')';
                            }
                        }
                    }
                }
            }
        });
        return true;
    }

    function initProvinceDemographicsChart() {
        var classic = document.getElementById('province-classic-view');
        if (classic && classic.hidden) return false;

        var data = parseDemographicsData();
        if (!data) return false;

        if (typeof Chart === 'undefined') return false;

        return renderChart(data);
    }

    function scheduleInit() {
        if (initProvinceDemographicsChart()) return;
        window.addEventListener('load', function onLoad() {
            window.removeEventListener('load', onLoad);
            initProvinceDemographicsChart();
        }, { once: true });
    }

    window.initProvinceDemographicsChart = function () {
        requestAnimationFrame(function () {
            if (!initProvinceDemographicsChart()) scheduleInit();
        });
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', scheduleInit);
    } else {
        scheduleInit();
    }
})();
