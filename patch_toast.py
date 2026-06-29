import re

with open("templates/world_map.html", "r") as f:
    content = f.read()

toast_css = """
    .toast-message {
        position: fixed;
        bottom: 20px;
        right: 20px;
        color: #fff;
        padding: 12px 24px;
        border-radius: 8px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.5);
        z-index: 1000;
        opacity: 0;
        transition: opacity 0.3s ease, transform 0.3s ease;
        transform: translateY(20px);
        font-family: 'Inter', sans-serif;
        font-weight: 500;
        pointer-events: none;
    }
    .toast-message.show {
        opacity: 1;
        transform: translateY(0);
    }
    .toast-success { background: rgba(30, 200, 100, 0.9); border: 1px solid #1ec864; }
    .toast-error { background: rgba(255, 50, 100, 0.9); border: 1px solid #ff3264; }
"""

toast_js = """
    function showToast(message, type = 'success') {
        const toast = document.createElement('div');
        toast.className = `toast-message toast-${type}`;
        toast.innerText = message;
        document.body.appendChild(toast);
        
        // Trigger reflow
        void toast.offsetWidth;
        
        toast.classList.add('show');
        
        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => toast.remove(), 300);
        }, 3000);
    }
"""

if ".toast-message" not in content:
    content = content.replace("</style>", toast_css + "</style>")

if "function showToast" not in content:
    content = content.replace("function closeSidebar() {", toast_js + "\n    function closeSidebar() {")

# Replace alerts
content = content.replace('alert(data.message);', 'showToast(data.message, data.status === "success" ? "success" : "error");')
content = content.replace('alert("Network error declaring siege.");', 'showToast("Network error declaring siege.", "error");')

with open("templates/world_map.html", "w") as f:
    f.write(content)
