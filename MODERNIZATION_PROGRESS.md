# Modernization Progress - Event Handler Refactoring

## Summary

Modernizing HTML templates to use `addEventListener` instead of inline `onclick` attributes. This follows best practices and allows ESLint to properly detect unused functions.

## Completed ✅

### 1. base.html
- **Before:** `<button onclick="clearAllCache()">`
- **After:** `<button id="clear-cache-btn">` + event listener in DOMContentLoaded
- **Pattern:** Simple button with ID

### 2. accounts.html (5 handlers refactored)
- **Buttons modernized:**
  - Add Account button (`#add-account-btn`)
  - Save Account button (`#save-account-btn`)
  - Edit/Delete/Sync/Test/View Categories (data attributes with event delegation)
  
- **Pattern used:** Event delegation on `#accounts-list` container
  ```javascript
  accountsList.addEventListener('click', async (e) => {
    const button = e.target.closest('button[data-action]');
    if (!button) return;
    const action = button.dataset.action;
    // Switch on action type
  });
  ```

- **Dynamic buttons:** `data-action="edit"` `data-account-id="${id}"`

### 3. filters.html (4 handlers refactored)
- **Buttons modernized:**
  - Add Filter button (`#add-filter-btn`)
  - Save Filter button (`#save-filter-btn`)
  - Account selector change event (`#accountSelect`)
  - Filter type change event (`#filterType`)
  - Edit/Delete (data attributes with event delegation)

- **Pattern:** Same event delegation pattern on `#filters-list`

## In Progress 🔄

### 4. rulesets.html (20+ handlers)
**Complexity:** High - many nested modals and dynamic content

**Handlers to refactor:**
1. Create Default Ruleset button
2. Show Create Ruleset Modal
3. Process All Tags button
4. Process Account Tags button  
5. Show Create Playlist Modal
6. Save Ruleset button
7. Save Rule button
8. Save Playlist button
9. Show Ruleset Rules button (dynamic)
10. Show Assign Ruleset button (dynamic)
11. Edit Ruleset button (dynamic)
12. Delete Ruleset button (dynamic)
13. Show Create Rule Modal button (dynamic)
14. Edit Rule button (dynamic)
15. Delete Rule button (dynamic)
16. Assign Ruleset button (in dynamically generated lists)
17. Unassign Ruleset button (in dynamically generated lists)

**Recommended approach:**
- Use multiple event delegation containers:
  - `#rulesets-container` for ruleset operations
  - `#rules-list` for rule operations  
  - `#assign-modal-content` for assignment operations
- Add data attributes: `data-action`, `data-ruleset-id`, `data-rule-id`, `data-account-id`

### 5. test.html (4 handlers)
**Handlers:**
1. Load Preview button
2. Download Playlist button
3. Remove Tag button (dynamic, multiple)
4. Create Manual Tag Rule button (dynamic, multiple)

**Recommended approach:**
- Event delegation on `#channel-preview-container`
- Data attributes for channel IDs and tag names

## Remaining Work

### Update ESLint Config
Once all templates are modernized, remove the ignore patterns from `.eslintrc.js`:

```javascript
// REMOVE THESE LINES:
'varsIgnorePattern': '^(new|edit|save|delete|sync|test|view|show|assign|unassign|process|clear|remove|download|create)[A-Za-z]|^(currentRuleset|collapse|totalTags)$',
'argsIgnorePattern': '^_|^(streamId)$'

// REPLACE WITH:
'varsIgnorePattern': '^_',
'argsIgnorePattern': '^_'
```

This will let ESLint catch actual unused functions while the event handlers are properly attached.

## Benefits of This Refactoring

1. **Better ESLint detection** - Can now catch genuinely unused functions
2. **Separation of concerns** - HTML structure separate from behavior
3. **Event delegation** - More efficient for dynamically generated content
4. **Easier testing** - Event handlers can be easily mocked/tested
5. **Modern best practices** - Follows current JavaScript standards
6. **CSP compatible** - Works with Content Security Policy restrictions

## Pattern Reference

### For Static Buttons
```html
<!-- Old -->
<button onclick="myFunction()">Click</button>

<!-- New -->
<button id="my-button">Click</button>

<script>
document.addEventListener('DOMContentLoaded', () => {
  const btn = document.getElementById('my-button');
  if (btn) {
    btn.addEventListener('click', () => myFunction());
  }
});
</script>
```

### For Dynamic Buttons (Event Delegation)
```html
<!-- Old -->
<button onclick="editItem(${id})">Edit</button>

<!-- New -->
<button data-action="edit" data-item-id="${id}">Edit</button>

<script>
const container = document.getElementById('items-list');
if (container) {
  container.addEventListener('click', (e) => {
    const button = e.target.closest('button[data-action]');
    if (!button) return;
    
    const action = button.dataset.action;
    const itemId = parseInt(button.dataset.itemId);
    
    if (action === 'edit') {
      editItem(itemId);
    }
  });
}
</script>
```

### For Select/Input Changes
```html
<!-- Old -->
<select onchange="handleChange()">

<!-- New -->
<select id="my-select">

<script>
const select = document.getElementById('my-select');
if (select) {
  select.addEventListener('change', () => handleChange());
}
</script>
```

## Testing Checklist

After refactoring each template:

- [ ] All buttons still work as expected
- [ ] Modal forms submit correctly
- [ ] Dynamic content buttons function properly
- [ ] No JavaScript errors in console
- [ ] ESLint shows no unused function errors
- [ ] All event handlers fire correctly
