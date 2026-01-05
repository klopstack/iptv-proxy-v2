# Tag Rule is_ppv Field - Quick Reference

## What is it?

A new field on tag rules that lets you control whether channels matching a pattern should be marked as PPV (pay-per-view) or not.

## When to use it?

**Problem:** Category says "PPV" but channels aren't actually pay-per-view events.

**Example:** Bally Sports/FanDuel Sports Network channels in a "Bally Sports PPV" category.

## Three Options

1. **`keep`** (default) - Don't change the is_ppv value
2. **`set_true`** - Mark matching channels as PPV
3. **`set_false`** - Mark matching channels as NOT PPV

## Example Rule

**Fix Bally Sports channels incorrectly marked as PPV:**

```json
{
  "name": "Bally Sports Not PPV",
  "pattern": "Bally Sports|FanDuel Sports",
  "pattern_type": "regex",
  "source": "category_name",
  "tag_name": "REGIONAL",
  "remove_from_name": false,
  "priority": 10,
  "set_is_ppv": "set_false"
}
```

**What this does:**
- Matches any category containing "Bally Sports" or "FanDuel Sports"
- Adds "REGIONAL" tag to channels
- Sets `is_ppv=false` on those channels (overriding category setting)

## How it works

1. Tag rules run in **priority order** (lower numbers first: 10 before 20)
2. **First matching rule with set_true/set_false wins**
3. Subsequent rules with `keep` don't override previous directives
4. Changes only apply during **tag reprocessing** (not automatic)

## Testing the rule

1. Create the rule via API or UI
2. Go to Account Settings
3. Click "Reprocess Tags"
4. Check logs for "is_ppv changed" count
5. Verify channels in your playlist

## Common Patterns

### Mark all PPV category channels as PPV
```json
{
  "pattern": "PPV|Pay Per View",
  "pattern_type": "regex",
  "source": "category_name",
  "set_is_ppv": "set_true"
}
```

### Unmark sports channels in PPV categories
```json
{
  "pattern": "Bally|FanDuel|MSG|NESN",
  "pattern_type": "regex",
  "source": "category_name",
  "set_is_ppv": "set_false"
}
```

### Mark specific fight/event channels as PPV
```json
{
  "pattern": "UFC|Boxing Match|WWE",
  "pattern_type": "regex",
  "source": "channel_name",
  "set_is_ppv": "set_true"
}
```

## Priority Examples

**Scenario:** Override general PPV marking for specific cases

```json
// Rule 1: Priority 10 (runs first)
{
  "pattern": "Bally Sports",
  "set_is_ppv": "set_false"  // NOT PPV
}

// Rule 2: Priority 20 (runs second)
{
  "pattern": "PPV",
  "set_is_ppv": "set_true"   // IS PPV
}

// Result: Bally Sports channels marked NOT PPV even in PPV category
```

**Why?** Lower priority (10) runs before higher priority (20). First match with set_true/set_false wins.

## Troubleshooting

**Changes not applying?**
- Run "Reprocess Tags" from account settings
- Check rule is enabled
- Verify pattern matches (test with tag extraction)
- Check rule priority order

**Wrong channels affected?**
- Test pattern with fewer channels first
- Use more specific patterns
- Check source: `channel_name` vs `category_name`

**Conflicts between rules?**
- Lower priority number wins
- First matching rule with set_true/set_false wins
- Adjust priorities to get desired behavior

## API Example

**Create rule via API:**

```bash
POST /rulesets/<ruleset_id>/rules
Content-Type: application/json

{
  "name": "Bally Sports Not PPV",
  "pattern": "Bally Sports",
  "pattern_type": "contains",
  "source": "category_name",
  "tag_name": "REGIONAL",
  "remove_from_name": false,
  "priority": 10,
  "enabled": true,
  "set_is_ppv": "set_false"
}
```

**Update existing rule:**

```bash
PATCH /rulesets/<ruleset_id>/rules/<rule_id>
Content-Type: application/json

{
  "set_is_ppv": "set_false"
}
```

## Best Practices

1. **Start specific:** Test with one channel first, then expand
2. **Use clear naming:** Include "PPV" or "Not PPV" in rule names
3. **Document why:** Add notes about which categories/channels the rule targets
4. **Test before production:** Use preview playlist feature to verify
5. **Lower priority for overrides:** Put exception rules at priority 10, general rules at 20+

## FAQ

**Q: Does this affect EPG matching?**  
A: No, EPG matching is separate. This only controls the is_ppv flag on channels.

**Q: Can I mark channels as PPV that aren't in a PPV category?**  
A: Yes! Use `set_is_ppv="set_true"` on any matching pattern.

**Q: What happens if multiple rules match?**  
A: First rule (by priority) with set_true/set_false wins. Subsequent rules with `keep` won't override.

**Q: Do I need to sync channels again?**  
A: No, just run "Reprocess Tags" to apply the directive.

**Q: Can I bulk-apply this to multiple accounts?**  
A: Yes, use rulesets and assign them to multiple accounts. The directive applies during each account's tag reprocessing.
