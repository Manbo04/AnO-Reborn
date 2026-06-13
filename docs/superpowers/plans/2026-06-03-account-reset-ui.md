# Account Reset UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Account Reset UI to templates/account.html including button, modal, and resource display.

**Architecture:** Frontend UI update using existing template patterns and custom modals.

**Tech Stack:** Jinja2 templates, HTML, CSS, Vanilla JavaScript.

---

### Task 1: Add Reset Button to Danger Zone

**Files:**
- Modify: `templates/account.html` around line 300 (Danger Zone section).

- [ ] **Step 1: Locate Danger Zone and add Reset Button**

```html
<div class="templatedivflex2left">
    <button type="button" onclick="confirmResetAccount()" class="templatedivbutton templatecenteredbutton redactionbutton">
        <span class="material-icons-outlined">restart_alt</span>Reset Account
    </button>
</div>
```

- [ ] **Step 2: Verify button appearance**

- [ ] **Step 3: Commit**

### Task 2: Implement Reset Confirmation Modal

**Files:**
- Modify: `templates/account.html` near other modals (bottom of file).

- [ ] **Step 1: Add Modal HTML**

```html
<div id="resetAccountModal" class="confirmation-modal" style="display: none;">
    <div class="modal-content">
        <h2><span class="material-icons-outlined" style="color: #ff9800;">restart_alt</span> Reset Account</h2>
        <p>Do you want to keep your current resources or start from scratch with the starter kit?</p>
        
        <div class="starter-kit-display" style="text-align: left; background: rgba(0,0,0,0.2); padding: 10px; border-radius: 5px; margin-bottom: 15px;">
            <p style="margin-bottom: 5px; font-weight: bold; color: #ff9800;">Starter Kit Includes:</p>
            <ul style="list-style: none; padding: 0; display: grid; grid-template-columns: 1fr 1fr; gap: 5px; font-size: 0.9em;">
                <li>Lumber: 120,000</li>
                <li>Iron: 50,000</li>
                <li>Coal: 50,000</li>
                <li>Rations: 350,000</li>
                <li>Steel: 15,000</li>
                <li>Components: 10,000</li>
                <li>Aluminium: 10,000</li>
            </ul>
        </div>

        <div class="modal-buttons" style="flex-direction: column; gap: 10px;">
            <button onclick="executeReset('keep')" class="templatedivbutton">Reset & Keep Resources</button>
            <button onclick="executeReset('full')" class="templatedivbutton redactionbutton">Full Reset (Starter Kit)</button>
            <button onclick="closeResetModal()" class="templatedivbutton" style="background: none; border: 1px solid #444;">Cancel</button>
        </div>
    </div>
</div>
```

- [ ] **Step 2: Commit**

### Task 3: Add JavaScript Control Logic

**Files:**
- Modify: `templates/account.html` inside the `<script>` tag.

- [ ] **Step 1: Add modal control functions**

```javascript
function confirmResetAccount() {
    document.getElementById('resetAccountModal').style.display = 'flex';
}

function closeResetModal() {
    document.getElementById('resetAccountModal').style.display = 'none';
}

function executeReset(type) {
    const form = document.createElement('form');
    form.method = 'POST';
    form.action = '/reset_account';
    
    const csrf = document.createElement('input');
    csrf.type = 'hidden';
    csrf.name = 'csrf_token';
    csrf.value = '{% if csrf_token is defined %}{{ csrf_token() }}{% endif %}';
    form.appendChild(csrf);
    
    const resetType = document.createElement('input');
    resetType.type = 'hidden';
    resetType.name = 'reset_type';
    resetType.value = type;
    form.appendChild(resetType);
    
    document.body.appendChild(form);
    form.submit();
}
```

- [ ] **Step 2: Add event listener for clicking outside and Escape key**

```javascript
document.getElementById('resetAccountModal').addEventListener('click', function(e) {
    if (e.target === this) closeResetModal();
});
// Update Escape key handler if needed (already exists for other modals)
```

- [ ] **Step 3: Commit**

