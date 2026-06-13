# Account Reset UI Design

**Goal:** Implement UI for 'Account Reset' feature in `templates/account.html`.

## UI Components

### 1. Danger Zone Button
Add a 'Reset Account' button next to 'Delete account'.
- **Style:** `templatedivbutton templatecenteredbutton redactionbutton` (same as delete).
- **Text:** "Reset Account"
- **Icon:** `restart_alt` or `settings_backup_restore`.

### 2. Reset Confirmation Modal
- **Trigger:** Clicking 'Reset Account' button.
- **Header:** "Reset Account" with `restart_alt` icon.
- **Content:**
    - "Do you want to keep your current resources or start from scratch with the starter kit?"
    - **Starter Kit Values Display:**
        - Lumber: 120k
        - Iron: 50k
        - Coal: 50k
        - Rations: 350k
        - Steel: 15k
        - Components: 10k
        - Aluminium: 10k
- **Buttons:**
    - "Cancel" (Close modal)
    - "Reset & Keep Resources" (Submit with `reset_type=keep`)
    - "Full Reset (Starter Kit)" (Submit with `reset_type=full`)

## Implementation Details

- **Modal HTML:** Similar structure to `deleteAccountModal`.
- **Styling:** Use existing `.confirmation-modal` classes.
- **JavaScript:**
    - `confirmResetAccount()` to show modal.
    - `closeResetModal()` to hide modal.
    - `executeReset(type)` to create and submit a POST form to `/reset_account`.
- **Form Submission:** POST to `/reset_account` with `reset_type` parameter and `csrf_token`.

